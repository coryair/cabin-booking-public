import { describe, expect, test } from "bun:test";

import { createSingleFlightTask } from "./singleFlight";

describe("createSingleFlightTask", () => {
  test("runs the underlying async task only once", async () => {
    let calls = 0;

    const run = createSingleFlightTask(async () => {
      calls += 1;
      return "done";
    });

    const [first, second, third] = await Promise.all([run(), run(), run()]);

    expect(first).toBe("done");
    expect(second).toBe("done");
    expect(third).toBe("done");
    expect(calls).toBe(1);
  });
});
