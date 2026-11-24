export function buildOnboardingSuccessPath(courseId, sourceCount) {
  const query = new URLSearchParams({
    created: "1",
    processing: "1",
    sourceCount: String(Number(sourceCount || 0)),
  });
  return `/courses/detail/${courseId}?${query.toString()}`;
}
