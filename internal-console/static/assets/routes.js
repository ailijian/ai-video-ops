export function matchWorkflowRoute(path) {
  const caseMatch = path.match(/^\/cases\/(\d{10,24})$/);
  if (caseMatch) return { name: "case-detail", value: caseMatch[1] };
  const taskMatch = path.match(/^\/tasks\/(case-[A-Za-z0-9_-]+)$/);
  if (taskMatch) return { name: "task-detail", value: taskMatch[1] };
  return null;
}
