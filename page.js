"use strict";

async function showBenchmark() {
  const response = await fetch("benchmarks.json", {cache: "no-cache"});
  if (!response.ok) throw new Error("Benchmark data unavailable");
  const {milestones} = await response.json();
  const latest = milestones[milestones.length - 1];
  document.querySelector("#fps").textContent = latest.average_fps.toFixed(1);
  document.querySelector("#bar").style.width = Math.min(100, latest.average_fps / 120 * 100) + "%";
  const date = document.querySelector("#date");
  date.dateTime = latest.date;
  date.textContent = new Date(latest.date + "T12:00:00Z").toLocaleDateString("en", {month:"long", day:"numeric", year:"numeric", timeZone:"UTC"});
  const body = document.querySelector("#routes");
  for (const route of latest.routes) {
    const row = body.insertRow();
    for (const value of [route.name, route.frames, route.fps.toFixed(2), route.p95_ms.toFixed(1) + " ms"]) {
      row.insertCell().textContent = value;
    }
  }
  document.querySelector("#display").textContent = latest.display_note;
  document.querySelector("#milestone").textContent = "Next movement milestone: " + (latest.average_fps + 10).toFixed(1) + " FPS.";
}
showBenchmark().catch(() => {
  document.querySelector("#fps").textContent = "—";
  document.querySelector("#display").textContent = "The benchmark data could not be loaded.";
});
