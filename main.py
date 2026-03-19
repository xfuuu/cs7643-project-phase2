from __future__ import annotations

import argparse

from pipeline import CrimeMysteryPipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI crime-mystery story generation pipeline")
    parser.add_argument("--output-dir", default="outputs", help="Directory where generated artifacts are saved.")
    parser.add_argument("--gemini-api-key", required=True, help="Gemini API key used for case generation, plot planning, and story realization.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pipeline = CrimeMysteryPipeline(output_dir=args.output_dir, gemini_api_key=args.gemini_api_key)
    results = pipeline.run()
    report = results["validation_report"]
    print(f"Generated setting: {results['case_bible'].setting[:80]}...")
    print(f"Validation passed: {report.is_valid}")
    print(f"Output directory: {results['output_dir']}")


if __name__ == "__main__":
    main()
