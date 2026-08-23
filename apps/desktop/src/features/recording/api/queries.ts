import { useQuery } from "@tanstack/react-query";
import { recordingKeys } from "@/features/recording/api/keys";
import {
  recordingApi,
  type RecordingSession,
} from "@/features/recording/api/recordings";

export function useRecordingSessions() {
  return useQuery({
    queryKey: recordingKeys.unfinished(),
    queryFn: recordingApi.list,
  });
}

export function blocksNewRecording(session: RecordingSession) {
  return session.state === "RECORDING" || session.state === "PAUSED";
}
