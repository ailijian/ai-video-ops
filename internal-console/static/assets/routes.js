export function matchWorkflowRoute(path) {
  const caseMatch = path.match(
    /^\/cases\/(\d{10,24})$/,
  );

  if (caseMatch) {
    return {
      name: "case-detail",
      value: caseMatch[1],
    };
  }

  const speakerNewMatch = path.match(
    /^\/customers\/([a-z0-9][a-z0-9_]{1,127})\/speakers\/new$/,
  );

  if (speakerNewMatch) {
    return {
      name: "speaker-new",
      businessId: speakerNewMatch[1],
    };
  }

  const speakerDetailMatch = path.match(
    /^\/customers\/([a-z0-9][a-z0-9_]{1,127})\/speakers\/([a-z0-9][a-z0-9_-]{1,127})$/,
  );

  if (speakerDetailMatch) {
    return {
      name: "speaker-detail",
      businessId: speakerDetailMatch[1],
      speakerId: speakerDetailMatch[2],
    };
  }

  const customerContentOperationsMatch =
    path.match(
      /^\/customers\/([a-z0-9][a-z0-9_]{1,127})\/content$/,
    );

  if (customerContentOperationsMatch) {
    return {
      name: "customer-content-operations",
      value:
        customerContentOperationsMatch[1],
    };
  }

  const customerEditMatch = path.match(
    /^\/customers\/([a-z0-9][a-z0-9_]{1,127})\/edit$/,
  );

  if (customerEditMatch) {
    return {
      name: "customer-edit",
      value: customerEditMatch[1],
    };
  }

  const customerSupplementMatch = path.match(
    /^\/customers\/([a-z0-9][a-z0-9_]{1,127})\/supplement$/,
  );

  if (customerSupplementMatch) {
    return {
      name: "customer-supplement",
      value: customerSupplementMatch[1],
    };
  }

  const customerMatch = path.match(
    /^\/customers\/([a-z0-9][a-z0-9_]{1,127})$/,
  );

  if (customerMatch) {
    return {
      name: "customer-detail",
      value: customerMatch[1],
    };
  }

  const taskMatch = path.match(
    /^\/tasks\/([A-Za-z0-9_-]+)$/,
  );

  if (taskMatch) {
    return {
      name: "task-detail",
      value: taskMatch[1],
    };
  }

  return null;
}
