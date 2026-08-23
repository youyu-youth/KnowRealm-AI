export const recordingKeys = {
  all: ["recording-sessions"] as const,
  unfinished: () => [...recordingKeys.all, "unfinished"] as const,
};
