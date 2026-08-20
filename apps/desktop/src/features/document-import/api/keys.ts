export const documentImportKeys = {
  job: (jobId: string) => ["processing-jobs", jobId] as const,
};
