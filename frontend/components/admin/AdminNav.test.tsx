import { describe, expect, test } from "bun:test";

import { getAdminSections } from "./AdminNav";

describe("getAdminSections", () => {
  test("limits analytics users to overview and analytics", () => {
    const sections = getAdminSections({
      isAnalytics: true,
      isSuperadmin: false,
    }).map((section) => section.id);

    expect(sections).toEqual(["overview", "analytics"]);
  });
});
