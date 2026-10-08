// k6 scenarios for SPEC §2.1 (open model: requests arrive at a fixed rate regardless of
// latency, which is what a TPS target means). Run via `make load-k6` (inside the compose
// network, so no host install is needed).
//   PROFILE=sustained  10 booking + 100 availability TPS (+ ~15% cancels), DURATION=10m
//   PROFILE=stress     50 booking + 500 availability TPS, DURATION=60s
import http from "k6/http";
import { check } from "k6";
import { randomIntBetween, randomItem, uuidv4 } from "https://jslib.k6.io/k6-utils/1.4.0/index.js";

const BASE = __ENV.BASE_URL || "http://web:8000";
const PROFILE = __ENV.PROFILE || "sustained";
const RATES = { sustained: [10, 100], stress: [50, 500] }[PROFILE];
const DURATION = __ENV.DURATION || (PROFILE === "stress" ? "60s" : "10m");
const DEALERSHIPS = Number(__ENV.LOAD_DEALERSHIPS || 50);
const CUSTOMERS = Number(__ENV.LOAD_CUSTOMERS || 5000);
const DURATIONS = { 1: 30, 2: 90, 3: 120 };

function scenario(rate, exec) {
  return {
    executor: "constant-arrival-rate", rate, timeUnit: "1s", duration: DURATION,
    preAllocatedVUs: rate * 2, maxVUs: rate * 10, exec,
  };
}

export const options = {
  scenarios: { booking: scenario(RATES[0], "book"), availability: scenario(RATES[1], "availability") },
  thresholds: {
    "http_req_duration{scenario:booking}": ["p(95)<300", "p(99)<800"],
    "http_req_duration{scenario:availability}": ["p(95)<150"],
    "checks": ["rate>0.999"],
  },
  summaryTrendStats: ["avg", "med", "p(90)", "p(95)", "p(99)", "max"],
};

// Load dealerships are Europe/London, 08:00-18:00. k6's JS runtime has no IANA timezone
// data, so apply the fixed UK rule: BST (UTC+1) from the last Sunday of March to the last
// Sunday of October.
function randomDay() {
  const d = new Date(Date.now() + randomIntBetween(21, 80) * 86400000);
  return d.toISOString().slice(0, 10);
}

function lastSunday(year, monthIndex) {
  const last = new Date(Date.UTC(year, monthIndex + 1, 0));
  return new Date(Date.UTC(year, monthIndex, last.getUTCDate() - last.getUTCDay()));
}

function utcOffsetMinutes(day) {
  const date = new Date(`${day}T12:00:00Z`);
  const year = date.getUTCFullYear();
  const bst = date >= lastSunday(year, 2) && date < lastSunday(year, 9);
  return bst ? 60 : 0;
}

function randomStart(serviceType, day) {
  const last = 18 * 60 - DURATIONS[serviceType];
  const minutes = 8 * 60 + 15 * randomIntBetween(0, Math.floor((last - 8 * 60) / 15));
  const utcMinutes = minutes - utcOffsetMinutes(day);
  const hh = String(Math.floor(utcMinutes / 60)).padStart(2, "0");
  const mm = String(utcMinutes % 60).padStart(2, "0");
  return `${day}T${hh}:${mm}:00Z`;
}

export function book() {
  const customer = 100000 + randomIntBetween(1, CUSTOMERS);
  const serviceType = randomItem([1, 2, 3]);
  const body = {
    customer_id: customer, vehicle_id: customer, service_type_id: serviceType,
    dealership_id: 1000 + randomIntBetween(1, DEALERSHIPS),
    start_time: randomStart(serviceType, randomDay()),
  };
  const res = http.post(`${BASE}/api/v1/appointments/`, JSON.stringify(body), {
    headers: { "Content-Type": "application/json", "Idempotency-Key": uuidv4() },
    tags: { name: "POST /appointments" },
  });
  // 409 (no capacity / vehicle already booked) is a valid business outcome.
  check(res, { "booking 201 or 409": (r) => r.status === 201 || r.status === 409 });
  if (res.status === 201 && Math.random() < 0.15) {
    const del = http.del(`${BASE}/api/v1/appointments/${res.json("id")}/`, null, {
      tags: { name: "DELETE /appointments/{id}" },
    });
    check(del, { "cancel 204": (r) => r.status === 204 });
  }
}

export function availability() {
  const params = `dealership_id=${1000 + randomIntBetween(1, DEALERSHIPS)}` +
    `&service_type_id=${randomItem([1, 2, 3])}&date=${randomDay()}`;
  const res = http.get(`${BASE}/api/v1/availability/?${params}`, {
    tags: { name: "GET /availability" },
  });
  check(res, { "availability 200": (r) => r.status === 200 });
}
