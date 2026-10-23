import assert from "node:assert/strict";
import test from "node:test";
import { rememberToken, restoreToken } from "../src/token-storage.ts";

const key = "piradio-token";
const example = "test-only-" + "x".repeat(40);
function storage() {
  const values = new Map();
  return {
    getItem: (k) => values.get(k) ?? null,
    setItem: (k, v) => values.set(k, v),
    removeItem: (k) => values.delete(k),
  };
}
function reset() {
  globalThis.localStorage = storage();
  globalThis.sessionStorage = storage();
}

test("token survives a new browser session and can be forgotten", () => {
  reset();
  assert.equal(rememberToken(example), true);
  globalThis.sessionStorage = storage();
  assert.equal(restoreToken(), example);
  assert.equal(rememberToken(""), true);
  assert.equal(restoreToken(), "");
});
test("existing session token migrates once into persistent storage", () => {
  reset();
  sessionStorage.setItem(key, example);
  assert.equal(restoreToken(), example);
  assert.equal(localStorage.getItem(key), example);
  assert.equal(sessionStorage.getItem(key), null);
});
test("persistent token takes precedence over stale session data", () => {
  reset();
  localStorage.setItem(key, example);
  sessionStorage.setItem(key, "stale");
  assert.equal(restoreToken(), example);
  assert.equal(rememberToken(""), true);
  assert.equal(sessionStorage.getItem(key), null);
});
test("blocked persistent storage falls back to the session without crashing", () => {
  reset();
  globalThis.localStorage = {
    getItem() {
      throw new Error("Blocked");
    },
    setItem() {
      throw new Error("Blocked");
    },
    removeItem() {
      throw new Error("Blocked");
    },
  };
  assert.equal(rememberToken(example), false);
  assert.equal(restoreToken(), example);
  assert.equal(rememberToken(""), false);
  assert.equal(restoreToken(), "");
});
test("blocked session storage does not prevent persistent use", () => {
  reset();
  globalThis.sessionStorage = {
    getItem() {
      throw new Error("Blocked");
    },
    setItem() {
      throw new Error("Blocked");
    },
    removeItem() {
      throw new Error("Blocked");
    },
  };
  assert.equal(rememberToken(example), true);
  assert.equal(restoreToken(), example);
});
