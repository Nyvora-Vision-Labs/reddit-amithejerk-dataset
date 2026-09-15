"""Assign every r/AmITheJerk post to one of 10 real-life categories, judged by three models.

Claude, OpenAI and DeepSeek each label every post independently with the same prompt; the three
votes are combined into one label by build_categorized_data.py, which keeps a post when at least
two judges agree on its category.

Usage:
    python3 categorization/categorize_posts.py eval [JUDGE]   # accuracy on the hand-labeled gold_sample.json
    python3 categorization/categorize_posts.py run  [JUDGE]   # label all posts with one judge (resumable)
    python3 categorization/categorize_posts.py run  all       # every judge in turn
    python3 categorization/categorize_posts.py models         # list what each provider serves this account

JUDGE is claude, openai or deepseek (default: all). Each judge writes its own files, so a rerun
only re-asks the posts that judge has not answered yet:
    categorization/post_categories_<judge>.csv   +  post_categories_progress_<judge>.jsonl

API keys come from the environment or from .env in the project root:
    ANTHROPIC_API_KEY, OPENAI_API_KEY, DEEPSEEK_API_KEY
"""
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data_files" / "scraped_posts.csv"
OUT_DIR = ROOT / "categorization"
GOLD_PATH = OUT_DIR / "gold_sample.json"
ENV_PATH = ROOT / ".env"

WORKERS = int(os.environ.get("WORKERS", 16))  # concurrent requests per judge
MAX_RETRIES = 5

# Each judge is one model from one provider. The OpenAI model is resolved at runtime from the
# account's own model list (see pick_openai_model), since which GPT models an account serves varies.
JUDGES = {
    "claude": {"provider": "anthropic", "model": "claude-opus-5", "key": "ANTHROPIC_API_KEY"},
    "openai": {"provider": "openai", "model": None, "key": "OPENAI_API_KEY"},
    "deepseek": {"provider": "deepseek", "model": "deepseek-v4-pro", "key": "DEEPSEEK_API_KEY"},
}

CATEGORIES = {
    "family": "Parents, siblings, grandparents, aunts/uncles/cousins, in-laws, step-family (when the poster is NOT the "
              "parent of the child involved), estrangement, family dynamics.",
    "romantic_relationships": "Dating, boyfriends/girlfriends, spouses and partners as a couple, crushes, breakups, "
                              "cheating, sex, exes.",
    "parenting_children": "The poster (or their partner) raising, disciplining or caring for their own or step "
                          "children, pregnancy, babies, custody.",
    "friendships": "Friends and friend groups, best friends, falling out with friends, online/gaming/Discord friends "
                   "and communities.",
    "work": "Jobs, coworkers, bosses/managers, customers (from the employee's side), hiring, quitting, workplace rules.",
    "school": "Students, classmates, teachers, principals, bullying at school, grades, group projects, school clubs "
              "and teams.",
    "money_possessions": "The dispute is mainly about money or belongings: paying, splitting costs, lending/borrowing "
                         "money or items, debts, inheritance, sharing accounts/passwords/devices, damaged or taken "
                         "property.",
    "housing_neighbors": "Living arrangements: roommates, moving in/out, chores, noise, house rules, landlords/tenants, "
                         "neighbors, pets in the home or neighborhood.",
    "events_celebrations": "The dispute centers on an event: weddings, birthdays, holidays (Christmas, Thanksgiving), "
                           "parties, funerals, graduations, vacations/trips, invitations.",
    "strangers_public": "Strangers and public settings: flights/trains/buses/seats, stores, restaurants and service "
                        "workers (from the customer's side), parking lots, gyms, entitled strangers, online "
                        "strangers, police.",
}

SYSTEM_PROMPT = """You categorize posts from r/AmITheJerk, where people describe a conflict and ask whether they were in the wrong.
Pick the ONE category that best describes the real-life area of the conflict being judged.

Categories:
{categories}

When several categories fit, use the first rule that applies:
a. The dispute is centered on a specific event (wedding, birthday, holiday, party, trip) -> events_celebrations
b. It is mainly about money or belongings, even with family, friends or a partner -> money_possessions
c. It is mainly about living arrangements, roommates or neighbors -> housing_neighbors
d. The poster is acting as the parent of the child involved -> parenting_children
e. It happens in a work or school setting -> work or school
f. Otherwise choose by the relationship to the other person: family, romantic_relationships, friendships or strangers_public

Use the category "none" only when the post describes no categorizable conflict at all.
Also give a secondary_category if a second category clearly applies (otherwise "none"), and your confidence:
"high" (clearly one category), "medium" (a reasonable choice among two), or "low" (vague, off-topic, or too little text).
Judge only the category, not who is in the wrong.

Reply with JSON only, for example:
{{"category": "family", "secondary_category": "none", "confidence": "high"}}""".format(
    categories="\n".join(f"- {name}: {desc}" for name, desc in CATEGORIES.items())
)

LABEL_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": [*CATEGORIES, "none"]},
        "secondary_category": {"type": "string", "enum": [*CATEGORIES, "none"]},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["category", "secondary_category", "confidence"],
    "additionalProperties": False,
}


def paths_for(judge):
    """Output paths for one judge, so each model's pass stays separate and separately resumable."""
    return (OUT_DIR / f"post_categories_progress_{judge}.jsonl", OUT_DIR / f"post_categories_{judge}.csv")


def load_env():
    """Read .env into the environment without overriding variables that are already set.

    Tolerates the spaces-around-= style this project's .env uses (KEY = value).
    """
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        os.environ.setdefault(name.strip(), value.strip().strip("\"'"))


def api_key(judge):
    load_env()
    key = os.environ.get(JUDGES[judge]["key"])
    if not key:
        sys.exit(f"No API key for {judge}: set {JUDGES[judge]['key']} in the environment or in {ENV_PATH}")
    return key


def pick_openai_model(client):
    """Newest GPT chat model this account serves -- OpenAI's line-up differs per account."""
    skip = ("audio", "realtime", "image", "embedding", "tts", "transcribe", "search", "moderation", "instruct")
    models = [m for m in client.models.list().data
              if m.id.startswith("gpt") and not any(s in m.id for s in skip)]
    if not models:
        sys.exit("No GPT chat model available on this OpenAI account -- name one explicitly in JUDGES.")
    return max(models, key=lambda m: m.created or 0).id


def make_client(judge):
    """Returns (client, model) for one judge, using that provider's official SDK."""
    config = JUDGES[judge]
    key = api_key(judge)
    if config["provider"] == "anthropic":
        import anthropic
        return anthropic.Anthropic(api_key=key, max_retries=MAX_RETRIES, timeout=180.0), config["model"]

    from openai import OpenAI
    base_url = "https://api.deepseek.com" if config["provider"] == "deepseek" else None
    client = OpenAI(api_key=key, base_url=base_url, max_retries=MAX_RETRIES, timeout=180)
    if not config["model"]:
        config["model"] = pick_openai_model(client)  # resolve once, reuse for every post in this run
        print(f"{judge}: using {config['model']}", flush=True)
    return client, config["model"]


def normalize(data, usage):
    """Validate one reply and flatten it into the record written to the progress file."""
    if data.get("category") not in (*CATEGORIES, "none"):
        raise ValueError(f"unknown category {data.get('category')!r}")
    if data.get("secondary_category") not in (*CATEGORIES, "none"):
        data["secondary_category"] = "none"
    if data.get("confidence") not in ("high", "medium", "low"):
        data["confidence"] = None
    return {
        "category": data["category"],
        "secondary_category": data["secondary_category"],
        "confidence": data["confidence"],
        **usage,
    }


def ask_anthropic(client, model, title, content):
    response = client.beta.messages.create(
        model=model,
        max_tokens=4096,
        # the system prompt is identical for every post, so cache it; a 10-way label needs little thinking
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": f"<title>{title}</title>\n<post>{content}</post>"}],
        output_config={"format": {"type": "json_schema", "schema": LABEL_SCHEMA}, "effort": "low"},
        # a post about abuse or violence can trip a refusal; fall back rather than lose the row
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if response.stop_reason == "refusal":
        raise ValueError(f"refused: {getattr(response.stop_details, 'category', None)}")
    if response.stop_reason == "max_tokens":
        raise ValueError("hit max_tokens before finishing the JSON")
    text = next(b.text for b in response.content if b.type == "text")
    usage = response.usage
    return json.loads(text), {
        "input_tokens": usage.input_tokens,
        "cached_input_tokens": getattr(usage, "cache_read_input_tokens", None),
        "output_tokens": usage.output_tokens,
    }


def ask_openai_compatible(client, model, title, content):
    """OpenAI and DeepSeek share the chat-completions shape. max_tokens is left unset: the reply is a
    few dozen tokens, and the parameter is spelled differently across current OpenAI models."""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},  # identical for every post, so it caches
            {"role": "user", "content": f"<title>{title}</title>\n<post>{content}</post>"},
        ],
        response_format={"type": "json_object"},
    )
    usage = response.usage
    details = getattr(usage, "prompt_tokens_details", None)
    cached = getattr(usage, "prompt_cache_hit_tokens", None)
    if cached is None and details is not None:
        cached = getattr(details, "cached_tokens", None)
    return json.loads(response.choices[0].message.content), {
        "input_tokens": usage.prompt_tokens,
        "cached_input_tokens": cached,
        "output_tokens": usage.completion_tokens,
    }


def classify(judge, client, model, title, content):
    """Returns the parsed labels, retrying when a reply is not valid JSON with a known category."""
    ask = ask_anthropic if JUDGES[judge]["provider"] == "anthropic" else ask_openai_compatible
    last_error = None
    for _ in range(3):
        try:
            data, usage = ask(client, model, title, content)
            return normalize(data, usage)
        except (json.JSONDecodeError, StopIteration, TypeError, ValueError) as e:
            last_error = e
    raise RuntimeError(f"no valid label after 3 attempts: {last_error}")


def load_posts():
    df = pd.read_csv(DATA_PATH)
    df["row_id"] = df.index
    df["title"] = df["title"].fillna("").astype(str)
    df["content"] = df["content"].fillna("").astype(str)
    return df


def evaluate(judge):
    gold = {int(k): v for k, v in json.loads(GOLD_PATH.read_text()).items() if not k.startswith("_")}
    df = load_posts().loc[list(gold)]
    client, model = make_client(judge)
    with ThreadPoolExecutor(WORKERS) as pool:
        futures = {pool.submit(classify, judge, client, model, p.title, p.content): row_id
                   for row_id, p in df.iterrows()}
        results = {futures[f]: f.result() for f in as_completed(futures)}

    correct = either = 0
    for row_id, post in df.iterrows():
        res = results[row_id]
        ok = res["category"] == gold[row_id]
        correct += ok
        either += ok or res["secondary_category"] == gold[row_id]
        mark = "ok " if ok else "XX "
        print(f"{mark}{res['category']:22} {res['confidence']!s:6} gold={gold[row_id]:22} | {post.title[:60]}")
    n = len(df)
    print(f"\n{judge} ({model}): accuracy {correct}/{n} = {correct / n:.0%}, primary or secondary {either / n:.0%}")


def run(judge):
    progress_path, results_path = paths_for(judge)
    df = load_posts()
    done = set()
    if progress_path.exists():
        with open(progress_path) as f:
            done = {json.loads(line)["row_id"] for line in f if line.strip()}
    todo = df[~df["row_id"].isin(done)]
    client, model = make_client(judge)
    print(f"{judge} ({model}): {len(done)} already labeled, {len(todo)} to go", flush=True)

    lock = threading.Lock()
    failed = 0
    start = time.time()
    with open(progress_path, "a") as out, ThreadPoolExecutor(WORKERS) as pool:
        futures = {pool.submit(classify, judge, client, model, p.title, p.content): p.row_id
                   for p in todo.itertuples()}
        for n, future in enumerate(as_completed(futures), 1):
            row_id = futures[future]
            try:
                record = {"row_id": int(row_id), **future.result()}
            except Exception as e:  # leave it out of the progress file so a rerun retries it
                failed += 1
                print(f"row {row_id} failed: {e}", flush=True)
                continue
            with lock:
                out.write(json.dumps(record) + "\n")
                out.flush()
            if n % 250 == 0:
                rate = (time.time() - start) / n
                print(f"[{time.strftime('%H:%M:%S')}] {judge} {len(done) + n}/{len(df)} "
                      f"(~{rate * (len(todo) - n) / 60:.0f} min left, {failed} failed)", flush=True)

    with open(progress_path) as f:
        labels = pd.DataFrame([json.loads(line) for line in f if line.strip()]).drop_duplicates("row_id", keep="last")
    result = df[["row_id", "title", "link", "upvotes", "comments"]].merge(labels, on="row_id", how="left")
    result["model"] = model
    result.to_csv(results_path, index=False)

    print(f"DONE {judge}. Saved {results_path} ({result['category'].isna().sum()} posts without a label)")
    print(result["category"].value_counts().to_string())
    print("tokens: input {:,} (cached {:,}), output {:,}".format(
        int(labels.input_tokens.sum()), int(labels.cached_input_tokens.fillna(0).sum()),
        int(labels.output_tokens.sum())))


def list_models():
    """What each provider actually serves this account -- model line-ups drift."""
    load_env()
    from openai import OpenAI
    for judge, config in JUDGES.items():
        if not os.environ.get(config["key"]):
            print(f"{judge:9}: no {config['key']} set")
            continue
        try:
            if config["provider"] == "anthropic":
                import anthropic
                names = [m.id for m in anthropic.Anthropic(api_key=os.environ[config["key"]]).models.list()]
            else:
                base = "https://api.deepseek.com" if config["provider"] == "deepseek" else None
                names = [m.id for m in OpenAI(api_key=os.environ[config["key"]], base_url=base).models.list().data]
            print(f"{judge:9}: {', '.join(sorted(names))}")
        except Exception as e:
            print(f"{judge:9}: could not list models ({e})")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    target = sys.argv[2] if len(sys.argv) > 2 else "all"
    if target != "all" and target not in JUDGES:
        sys.exit(f"Unknown judge {target!r}. Pick one of: {', '.join(JUDGES)}, or all")
    judges = list(JUDGES) if target == "all" else [target]

    if cmd == "models":
        list_models()
    elif cmd == "eval":
        for j in judges:
            evaluate(j)
    elif cmd == "run":
        for j in judges:
            run(j)
    else:
        sys.exit(__doc__)
