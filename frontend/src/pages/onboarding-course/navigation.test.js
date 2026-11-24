import test from "node:test";
import assert from "node:assert/strict";

import { buildOnboardingSuccessPath } from "./navigation.js";

test("buildOnboardingSuccessPath sends users to the course detail page", () => {
  assert.equal(
    buildOnboardingSuccessPath("course_123", 2),
    "/courses/detail/course_123?created=1&processing=1&sourceCount=2"
  );
});
