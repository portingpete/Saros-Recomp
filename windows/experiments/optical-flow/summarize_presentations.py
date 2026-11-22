"""Recompute each route's presentation rate from the published stage reports."""
import csv
import gzip
import json
from collections import defaultdict
from pathlib import Path


def separated_timestamps(timestamps, minimum_ns):
    retained = []
    for timestamp in sorted(set(timestamps)):
        if not retained or timestamp - retained[-1] >= minimum_ns:
            retained.append(timestamp)
    return retained


def main():
    directory = Path(__file__).resolve().parent
    metadata = json.loads((directory / "measurements.json").read_bytes())
    samples = defaultdict(list)
    with gzip.open(directory / "per-present.csv.gz", "rt", newline="") as stream:
        for row in csv.DictReader(stream):
            key = row["variant"], row["route"]
            value = row["first_pixel_out_ns"]
            samples[key].append(int(value) if value else None)

    minimum_ns = 1e9 / (2 * metadata["monitor_hz"])
    print("Variant / route                      Reports   Distinct/s   Refresh-separated/s")
    for route in metadata["routes"]:
        key = route["variant"], route["route"]
        reports = samples.pop(key)
        positives = [stamp for stamp in reports if stamp is not None]
        distinct = len(set(positives))
        separated = len(separated_timestamps(positives, minimum_ns))
        duration_s = route["duration_ns"] / 1e9
        if len(reports) != route["complete_stage_reports"] or distinct != route["positive_distinct"]:
            raise ValueError(f"Published totals disagree for {key}")
        if round(distinct / duration_s, 3) != route["scanout_fps"]:
            raise ValueError(f"Published rate disagrees for {key}")
        if (separated != route["refresh_separated_timestamps"]
                or round(separated / duration_s, 3) != route["refresh_separated_fps"]):
            raise ValueError(f"Published refresh separation disagrees for {key}")
        label = " / ".join(key)
        print(f"{label:<38} {len(reports):>6}   {distinct/duration_s:>10.3f}   {separated/duration_s:>19.3f}")
    if samples:
        raise ValueError(f"Undocumented routes in the CSV: {list(samples)}")


if __name__ == "__main__":
    main()
