import json
import glob
import os

INPUT_DIR = "./manual-evaluations/criteria-conversion/"
OUTPUT_DIR = "./manual-evaluations/criteria-conversion-human/"
os.makedirs(OUTPUT_DIR, exist_ok=True)

TARGET_CLASSES = {"partial", "error"}


def ask_user(auto_class, explanation, text, logic):
    print("\n----------------------------------------")
    print(f"AUTO CLASSIFICATION: {auto_class}")
    print(f"LLM EXPLANATION: {explanation}")
    print("----------------------------------------")
    print(f"CRITERION: {text}")
    print("LOGIC:")
    print(json.dumps(logic, indent=2, ensure_ascii=False))
    print("----------------------------------------")
    print("Your evaluation:")
    print("  c = correct")
    print("  p = partial")
    print("  w = wrong")
    print("  s = skip")

    while True:
        choice = input("Enter choice (c/p/w/s): ").strip().lower()
        if choice in {"c", "p", "w", "s"}:
            return choice
        print("Invalid input. Try again.")

def convert_choice(choice):
    if choice == "c":
        return "correct"
    if choice == "p":
        return "partial"
    if choice == "w":
        return "wrong"
    return None


files = glob.glob(f"{INPUT_DIR}/manual_eval_*.json")
print(f"Found {len(files)} evaluation files to review.")

for file in files:
    base = os.path.basename(file)
    out_path = os.path.join(OUTPUT_DIR, base.replace("manual_eval_", "human_eval_"))

    if os.path.exists(out_path):
        print(f"Skipping {base} (already manually reviewed).")
        continue

    print(f"\n=== Reviewing {base} ===")

    with open(file, "r", encoding="utf-8") as f:
        data = json.load(f)

    total_criteria = len(data)
    auto_correct = sum(1 for x in data if x["evaluation"]["classification"] == "very_likely_correct")
    to_review = sum(1 for x in data if x["evaluation"]["classification"] in TARGET_CLASSES)

    print(f"Total criteria in this trial: {total_criteria}")
    print(f"Automatically correct (ignored): {auto_correct}")
    print(f"Criteria requiring manual review: {to_review}")
    print("----------------------------------------")

    human_results = []
    reviewed_count = 0

    for item in data:
        auto_class = item["evaluation"]["classification"]

        if auto_class not in TARGET_CLASSES:
            continue

        reviewed_count += 1
        print(f"\n[{reviewed_count}/{to_review}] Reviewing criterion ID {item['id']}")

        explanation = item["evaluation"].get("explanation", "No explanation provided.")

        choice = ask_user(
            auto_class,
            explanation,
            item["text"],
            item["logic"]
        )

        if choice == "s":
            continue

        human_results.append({
            "id": item["id"],
            "type": item["type"],
            "text": item["text"],
            "logic": item["logic"],
            "auto_classification": auto_class,
            "auto_explanation": explanation,
            "human_classification": convert_choice(choice)
        })

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(human_results, f, indent=4, ensure_ascii=False)

    print(f"Saved manual review → {out_path}")
    print(f"Completed: {reviewed_count}/{to_review} reviewed.")
