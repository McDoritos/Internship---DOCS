import json
import glob
import os
from groq import Groq
import time
import re

GROQ_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_KEY)

OUTPUT_DIR = "./llm-outputs/criteria-conversion/"
OUTPUT_FILES = glob.glob(f"{OUTPUT_DIR}/*-experiment-*.txt")

SAVE_DIR = "./manual-evaluations/criteria-conversion/"
os.makedirs(SAVE_DIR, exist_ok=True)

def safe_json_extract(text):
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch == "{":
            try:
                obj, _ = decoder.raw_decode(text[i:])
                return obj
            except:
                continue
    return None

PROMPT_TEMPLATE = """
You evaluate the correctness of a logical rule generated from a clinical trial eligibility criterion.

Your task:
Given:
1) ORIGINAL CRITERION (natural language)
2) LOGIC RULE (JSON)
3) TYPE: inclusion or exclusion criterion

Classify the rule as:
- "very_likely_correct"
- "partial"
- "likely_wrong"

Evaluation rules:

1. FIELD SELECTION (IMPORTANT)
- If the criterion can be mapped to one of the allowed schema fields, the rule MUST use that field.
- If the model used a custom field when a schema field exists → classify as "partial".
- If the model used a synonym instead of the normalized lab field → classify as "partial".
- If the model used a schema field incorrectly (wrong meaning) → classify as "likely_wrong".
- If the model used a custom field AND no schema field exists → this is acceptable → not penalized.

Allowed schema fields:
age, gender, diagnosis, stage, ecog_ps, molecular_status,
diagnosis_date, treatment, treatment_name,
treatment_start_date, treatment_end_date,
progression_date, death_date, control

Normalized lab fields:
leucocitos, neutrofilos, neutrofilos_percent,
linfocitos, linfocitos_percent,
monocitos, monocitos_percent,
eosinofilos, eosinofilos_percent,
basofilos, basofilos_percent,
eritrocitos, hemoglobina, hematocrito,
vc_medio, hcm, chcm, rdw,
plaquetas, vpm, plaquetocrito, pdw,
glicose, azoto_ureico, creatinina,
sodio, potassio, proteinas_totais, albumina,
calcio, osmolalidade, ldh, ast, alt,
fosfatase_alcalina, gama_gt, bilirrubina_total,
creatina_cinase

2. LOGIC ACCURACY
- If meaning is preserved and operators/values are correct → "very_likely_correct" (if fields are correct) or "partial" (if fields are imperfect).
- If meaning is partially preserved → "partial".
- If meaning is incorrect or inverted → "likely_wrong".

3. EXCLUSION SEMANTICS
- For exclusion criteria, the logic must evaluate TRUE when the exclusion condition is present.
- If inverted → "likely_wrong".

4. STRUCTURE
- JSON must be coherent.
- Boolean structure must be explicit.
- Structural issues → "partial" unless completely invalid → "likely_wrong".

Output ONLY:
{{
  "classification": "...",
  "explanation": "short explanation"
}}

TYPE:
{ctype}

ORIGINAL:
{criterion}

LOGIC:
{logic}
"""

def evaluate_rule(criterion_text, logic_json, ctype):
    prompt = PROMPT_TEMPLATE.format(
        ctype=ctype,
        criterion=criterion_text,
        logic=json.dumps(logic_json, ensure_ascii=False)
    )

    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0
            )

            content = response.choices[0].message.content.strip()

            if not content:
                print("Empty response from LLM, skipping.")
                return {"classification": "error", "explanation": "Empty LLM response"}

            match = re.search(r"\{.*\}", content, flags=re.DOTALL)
            if not match:
                print("No JSON found in LLM response, skipping.")
                return {"classification": "error", "explanation": "No JSON found in LLM response"}

            json_text = match.group(0)

            try:
                return json.loads(json_text)
            except Exception:
                print("Invalid JSON returned by LLM, skipping.")
                return {"classification": "error", "explanation": "Invalid JSON returned by LLM"}

        except Exception as e:
            print(f"LLM error: {e}. Retrying...")
            time.sleep(5)

    return {"classification": "error", "explanation": "LLM failure after retries"}


print(f"Found {len(OUTPUT_FILES)} model output files.")

for output_file in OUTPUT_FILES:
    model_name = os.path.basename(output_file).replace(".txt", "")

    print("\n==============================")
    print(f"Processing model file: {model_name}")
    print("==============================")

    with open(output_file, "r", encoding="utf-8") as f:
        raw_text = f.read()

    blocks = raw_text.split("Ouput for file ")
    blocks = [b for b in blocks if b.strip()]

    print(f"Found {len(blocks)} trial blocks inside this file.")

    trial_index = 0

    for block in blocks:
        trial_index += 1
        print(f"\nProcessing trial block #{trial_index}")

        header_line = block.split("\n")[0].strip()
        match = re.search(r"clinical-trial-extracted_(e\d+)\.txt", header_line)
        if match:
            trial_id = match.group(1)
        else:
            trial_id = f"unknown_{trial_index}"

        print(f"Trial ID detected: {trial_id}")
        
        save_path = os.path.join(
            SAVE_DIR,
            f"manual_eval_{model_name}_trial-{trial_id}.json"
        )

        if os.path.exists(save_path):
            print(f"Skipping trial {trial_id} (already evaluated).")
            continue


        model_output = safe_json_extract(block)

        if model_output is None:
            print("ERROR: Could not extract JSON from this block.")
            continue

        inc_count = len(model_output.get("inclusion_criteria", []))
        exc_count = len(model_output.get("exclusion_criteria", []))
        print(f"Inclusion criteria: {inc_count}")
        print(f"Exclusion criteria: {exc_count}")

        results = []

        for item in model_output.get("inclusion_criteria", []):
            if not isinstance(item, dict):
                print("Skipping invalid inclusion item (not a dict).")
                continue

            if "id" not in item or "text" not in item or "logic" not in item:
                print("Skipping inclusion item missing required fields.")
                continue

            print(f"Evaluating inclusion ID {item['id']}")
            eval_result = evaluate_rule(item["text"], item["logic"], "inclusion")

            results.append({
                "id": item["id"],
                "type": "inclusion",
                "text": item["text"],
                "logic": item["logic"],
                "evaluation": eval_result
            })


        for item in model_output.get("exclusion_criteria", []):
            if not isinstance(item, dict):
                print("Skipping invalid exclusion item (not a dict).")
                continue

            if "id" not in item or "text" not in item or "logic" not in item:
                print("Skipping exclusion item missing required fields.")
                continue

            print(f"Evaluating exclusion ID {item['id']}")
            eval_result = evaluate_rule(item["text"], item["logic"], "exclusion")

            results.append({
                "id": item["id"],
                "type": "exclusion",
                "text": item["text"],
                "logic": item["logic"],
                "evaluation": eval_result
            })

        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=4, ensure_ascii=False)

        print(f"Saved evaluation for trial {trial_id} → {save_path}")
