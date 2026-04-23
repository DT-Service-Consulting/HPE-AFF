import argparse
import json
import os
from core_logic import extract_pdf_form_fields, extract_pdf_text, evolve_mappings, fill_pdf_form


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--generations", type=int, default=3)
    parser.add_argument("--population", type=int, default=5)
    args = parser.parse_args()

    with open(args.data, "r", encoding="utf-8") as f:
        user_data = json.load(f)

    fields = extract_pdf_form_fields(args.pdf)
    form_text = extract_pdf_text(args.pdf)

    candidates = evolve_mappings(fields, user_data, form_text, generations=args.generations, population=args.population)
    best = candidates[0]

    os.makedirs("outputs", exist_ok=True)
    out_pdf = os.path.join("outputs", "filled.pdf")
    out_json = os.path.join("outputs", "best_mapping.json")

    fill_pdf_form(args.pdf, out_pdf, best.mapping, user_data)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(best.mapping, f, indent=2)

    print("Best mapping saved to:", out_json)
    print("Filled PDF saved to:", out_pdf)


if __name__ == "__main__":
    main()
