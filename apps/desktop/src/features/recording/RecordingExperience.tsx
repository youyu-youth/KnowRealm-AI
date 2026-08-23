import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleStop, EyeOff, Mic, Pause, Play } from "lucide-react";
import { useCallback, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { courseApi } from "@/features/courses/api/courses";
import { courseKeys } from "@/features/courses/api/keys";
import {
  captureBatchApi,
  type CaptureBatchAccepted,
} from "@/features/document-import/api/captureBatches";
import { recordKeys } from "@/features/records/api/keys";
import { recordingKeys } from "@/features/recording/api/keys";
import {
  recordingApi,
  type RecordingSession,
  type RecordingTargetState,
} from "@/features/recording/api/recordings";
import {
  blocksNewRecording,
  useRecordingSessions,
} from "@/features/recording/api/queries";
import { useRecordingUiStore } from "@/features/recording/store";
import {
  hideWindowTemporarily,
  setRecordingKeepAwake,
} from "@/services/tauri/recording";

const MIME_TYPE = "audio/webm;codecs=opus";
const AUDIO_BITS_PER_SECOND = 128_000;
const POC_CHUNK_MS = 20_000;
const MAX_DURATION_MS = 3 * 60 * 60 * 1_000;

type Props = {
  onAccepted: (result: CaptureBatchAccepted) => void | Promise<void>;
};

type Segment = { blob: Blob; durationMs: number };
const NO_RECORDING_SESSIONS: RecordingSession[] = [];

function formatDuration(durationMs: number) {
  const totalSeconds = Math.floor(durationMs / 1_000);
  const hours = Math.floor(totalSeconds / 3_600);
  const minutes = Math.floor((totalSeconds % 3_600) / 60);
  const seconds = totalSeconds % 60;
  return [hours, minutes, seconds]
    .map((value) => String(value).padStart(2, "0"))
    .join(":");
}

export function RecordingExperience({ onAccepted }: Props) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const startOpen = useRecordingUiStore((state) => state.startOpen);
  const activeSessionId = useRecordingUiStore((state) => state.activeSessionId);
  const title = useRecordingUiStore((state) => state.title);
  const courseId = useRecordingUiStore((state) => state.courseId);
  const confirmAbandon = useRecordingUiStore((state) => state.confirmAbandon);
  const busy = useRecordingUiStore((state) => state.busy);
  const error = useRecordingUiStore((state) => state.error);
  const elapsedMs = useRecordingUiStore((state) => state.elapsedMs);
  const setStartOpen = useRecordingUiStore((state) => state.setStartOpen);
  const setActiveSessionId = useRecordingUiStore(
    (state) => state.setActiveSessionId,
  );
  const setTitle = useRecordingUiStore((state) => state.setTitle);
  const setCourseId = useRecordingUiStore((state) => state.setCourseId);
  const setConfirmAbandon = useRecordingUiStore(
    (state) => state.setConfirmAbandon,
  );
  const setBusy = useRecordingUiStore((state) => state.setBusy);
  const setError = useRecordingUiStore((state) => state.setError);
  const setElapsedMs = useRecordingUiStore((state) => state.setElapsedMs);
  const resetDraft = useRecordingUiStore((state) => state.resetDraft);
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const segmentStartedAtRef = useRef(0);
  const segmentTimerRef = useRef<number | null>(null);
  const stopResolverRef = useRef<((segment: Segment) => void) | null>(null);
  const baseDurationRef = useRef(0);
  const sequenceRef = useRef(0);
  const operationRef = useRef<Promise<void>>(Promise.resolve());
  const attemptedFinalizingRef = useRef(new Set<string>());

  const courses = useQuery({
    queryKey: courseKeys.list(),
    queryFn: () => courseApi.list(),
    enabled: startOpen,
  });
  const activeCourses = (courses.data ?? []).filter(
    (course) => course.status === "ACTIVE",
  );
  const courseItems = [
    { value: "__none__", label: t("recording.noCourse") },
    ...activeCourses.map((course) => ({
      value: course.id,
      label: course.name,
    })),
  ];

  const sessionsQuery = useRecordingSessions();
  const unfinishedSessions = sessionsQuery.data ?? NO_RECORDING_SESSIONS;
  const attachedSession = unfinishedSessions.find(
    (item) => item.id === activeSessionId,
  );
  const displayedSession =
    attachedSession ??
    unfinishedSessions.find((item) => item.state === "FINALIZING") ??
    null;
  const recovery =
    unfinishedSessions.find(
      (item) => item.id !== activeSessionId && blocksNewRecording(item),
    ) ?? null;

  const cacheSession = useCallback(
    (updated: RecordingSession) => {
      queryClient.setQueryData<RecordingSession[]>(
        recordingKeys.unfinished(),
        (current) => {
          if (!current) return [updated];
          const index = current.findIndex((item) => item.id === updated.id);
          if (index < 0) return [...current, updated];
          return current.map((item) =>
            item.id === updated.id ? updated : item,
          );
        },
      );
      void queryClient.invalidateQueries({
        queryKey: recordingKeys.unfinished(),
        refetchType: "none",
      });
    },
    [queryClient],
  );

  const removeCachedSession = useCallback(
    (sessionId: string) => {
      queryClient.setQueryData<RecordingSession[]>(
        recordingKeys.unfinished(),
        (current) => current?.filter((item) => item.id !== sessionId) ?? [],
      );
      void queryClient.invalidateQueries({
        queryKey: recordingKeys.unfinished(),
        refetchType: "none",
      });
    },
    [queryClient],
  );

  const createSession = useMutation({
    mutationFn: ({
      selectedCourseId,
      recordingTitle,
    }: {
      selectedCourseId: string | null;
      recordingTitle: string;
    }) => recordingApi.create(selectedCourseId, recordingTitle),
    onSuccess: (created) => {
      setActiveSessionId(created.id);
      cacheSession(created);
    },
  });
  const appendChunk = useMutation({
    mutationFn: ({
      sessionId,
      sequenceNo,
      durationMs,
      targetState,
      blob,
    }: {
      sessionId: string;
      sequenceNo: number;
      durationMs: number;
      targetState: RecordingTargetState;
      blob: Blob;
    }) =>
      recordingApi.appendChunk(
        sessionId,
        sequenceNo,
        durationMs,
        targetState,
        blob,
      ),
    onSuccess: (accepted) => cacheSession(accepted.session),
  });
  const updateSession = useMutation({
    mutationFn: ({
      sessionId,
      targetState,
    }: {
      sessionId: string;
      targetState: "RECORDING" | "FINALIZING";
    }) => recordingApi.update(sessionId, targetState),
    onSuccess: cacheSession,
  });
  const abandonSession = useMutation({
    mutationFn: recordingApi.abandon,
    onSuccess: (_result, sessionId) => removeCachedSession(sessionId),
  });
  const handoffRecording = useMutation({
    mutationFn: (target: RecordingSession) =>
      captureBatchApi.createRecording(target.id),
  });
  const createSessionAsync = createSession.mutateAsync;
  const appendChunkAsync = appendChunk.mutateAsync;
  const updateSessionAsync = updateSession.mutateAsync;
  const abandonSessionAsync = abandonSession.mutateAsync;
  const handoffRecordingAsync = handoffRecording.mutateAsync;

  const runExclusive = useCallback((work: () => Promise<void>) => {
    operationRef.current = operationRef.current.then(work, work);
    return operationRef.current;
  }, []);

  const stopLocalCapture = useCallback(
    async (reportReleaseError = true) => {
      if (segmentTimerRef.current !== null) {
        window.clearTimeout(segmentTimerRef.current);
        segmentTimerRef.current = null;
      }
      if (recorderRef.current?.state === "recording")
        recorderRef.current.stop();
      recorderRef.current = null;
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      try {
        await setRecordingKeepAwake(false);
      } catch (releaseError) {
        if (reportReleaseError) {
          setError(
            releaseError instanceof Error
              ? releaseError.message
              : t("recording.errors.releaseKeepAwake"),
          );
        }
      }
    },
    [setError, t],
  );

  const finishHandoff = useCallback(
    async (target: RecordingSession) => {
      try {
        const wasAttached =
          useRecordingUiStore.getState().activeSessionId === target.id;
        const result = await handoffRecordingAsync(target);
        if (target.course_id) {
          await queryClient.invalidateQueries({
            queryKey: recordKeys.courseList(target.course_id),
          });
        }
        removeCachedSession(target.id);
        if (wasAttached) setActiveSessionId(null);
        if (
          wasAttached ||
          useRecordingUiStore.getState().activeSessionId === null
        ) {
          await onAccepted(result);
        }
      } catch (handoffError) {
        setError(
          handoffError instanceof Error
            ? handoffError.message
            : t("recording.errors.finalize"),
        );
      }
    },
    [
      handoffRecordingAsync,
      onAccepted,
      queryClient,
      removeCachedSession,
      setActiveSessionId,
      setError,
      t,
    ],
  );

  const appendSegment = useCallback(
    async (segment: Segment, targetState: RecordingTargetState) => {
      const currentId = useRecordingUiStore.getState().activeSessionId;
      const current = queryClient
        .getQueryData<RecordingSession[]>(recordingKeys.unfinished())
        ?.find((item) => item.id === currentId);
      if (!current) throw new Error(t("recording.errors.missingSession"));
      const accepted = await appendChunkAsync({
        sessionId: current.id,
        sequenceNo: sequenceRef.current,
        durationMs: segment.durationMs,
        targetState,
        blob: segment.blob,
      });
      sequenceRef.current += 1;
      baseDurationRef.current = accepted.session.recorded_duration_ms;
      setElapsedMs(accepted.session.recorded_duration_ms);
      if (!accepted.can_continue) {
        await stopLocalCapture();
        setError(t("recording.errors.lowDisk"));
      }
      return accepted.session;
    },
    [
      appendChunkAsync,
      queryClient,
      setElapsedMs,
      setError,
      stopLocalCapture,
      t,
    ],
  );

  const takeSegment = useCallback(() => {
    const recorder = recorderRef.current;
    if (!recorder || recorder.state !== "recording") {
      return Promise.reject(new Error(t("recording.errors.notRecording")));
    }
    if (segmentTimerRef.current !== null) {
      window.clearTimeout(segmentTimerRef.current);
      segmentTimerRef.current = null;
    }
    const durationMs = Math.max(
      1,
      Math.round(performance.now() - segmentStartedAtRef.current),
    );
    return new Promise<Segment>((resolve) => {
      stopResolverRef.current = ({ blob }) => resolve({ blob, durationMs });
      recorder.stop();
    });
  }, [t]);

  const queueCaptureFailure = useCallback(
    (failure: unknown) => {
      void stopLocalCapture();
      setActiveSessionId(null);
      setError(
        failure instanceof Error
          ? failure.message
          : t("recording.errors.capture"),
      );
    },
    [setActiveSessionId, setError, stopLocalCapture, t],
  );

  const openSegmentRef = useRef<() => void>(() => undefined);
  const rotateRef = useRef<() => void>(() => undefined);

  const openSegment = useCallback(() => {
    const stream = streamRef.current;
    if (!stream) throw new Error(t("recording.errors.microphone"));
    const chunks: Blob[] = [];
    const recorder = new MediaRecorder(stream, {
      mimeType: MIME_TYPE,
      audioBitsPerSecond: AUDIO_BITS_PER_SECOND,
    });
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunks.push(event.data);
    };
    recorder.onstop = () => {
      const resolve = stopResolverRef.current;
      stopResolverRef.current = null;
      resolve?.({ blob: new Blob(chunks, { type: MIME_TYPE }), durationMs: 0 });
    };
    recorder.onerror = () =>
      queueCaptureFailure(new Error(t("recording.errors.capture")));
    recorderRef.current = recorder;
    segmentStartedAtRef.current = performance.now();
    recorder.start();
    const remaining = MAX_DURATION_MS - baseDurationRef.current;
    segmentTimerRef.current = window.setTimeout(
      () => rotateRef.current(),
      Math.min(POC_CHUNK_MS, remaining),
    );
  }, [queueCaptureFailure, t]);
  useEffect(() => {
    openSegmentRef.current = openSegment;
  }, [openSegment]);

  const rotate = useCallback(() => {
    void runExclusive(async () => {
      try {
        const segment = await takeSegment();
        const reachesLimit =
          baseDurationRef.current + segment.durationMs >= MAX_DURATION_MS;
        if (!reachesLimit) openSegmentRef.current();
        const updated = await appendSegment(
          segment,
          reachesLimit ? "FINALIZING" : "RECORDING",
        );
        if (reachesLimit) {
          await stopLocalCapture();
          await finishHandoff(updated);
        }
      } catch (failure) {
        queueCaptureFailure(failure);
      }
    });
  }, [
    appendSegment,
    finishHandoff,
    queueCaptureFailure,
    runExclusive,
    stopLocalCapture,
    takeSegment,
  ]);
  useEffect(() => {
    rotateRef.current = rotate;
  }, [rotate]);

  const beginCapture = useCallback(
    async (target: RecordingSession, stream: MediaStream) => {
      await setRecordingKeepAwake(true);
      streamRef.current = stream;
      sequenceRef.current = target.chunk_count;
      baseDurationRef.current = target.recorded_duration_ms;
      setElapsedMs(target.recorded_duration_ms);
      setActiveSessionId(target.id);
      try {
        openSegmentRef.current();
      } catch (error) {
        await stopLocalCapture();
        throw error;
      }
    },
    [setActiveSessionId, setElapsedMs, stopLocalCapture],
  );

  const acquireMicrophone = useCallback(async () => {
    if (
      typeof MediaRecorder === "undefined" ||
      !MediaRecorder.isTypeSupported(MIME_TYPE)
    ) {
      throw new Error(t("recording.errors.unsupported"));
    }
    try {
      return await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      throw new Error(t("recording.errors.permission"));
    }
  }, [t]);

  async function handleStart(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    let stream: MediaStream | null = null;
    try {
      stream = await acquireMicrophone();
      const created = await createSessionAsync({
        selectedCourseId: courseId,
        recordingTitle: title.trim(),
      });
      try {
        await beginCapture(created, stream);
      } catch (failure) {
        stream.getTracks().forEach((track) => track.stop());
        await abandonSessionAsync(created.id).catch(() => undefined);
        setActiveSessionId(null);
        throw failure;
      }
      resetDraft();
      setStartOpen(false);
    } catch (startError) {
      stream?.getTracks().forEach((track) => track.stop());
      setError(
        startError instanceof Error
          ? startError.message
          : t("recording.errors.start"),
      );
    } finally {
      setBusy(false);
    }
  }

  function handlePause() {
    setBusy(true);
    setError(null);
    void runExclusive(async () => {
      try {
        const segment = await takeSegment();
        await appendSegment(segment, "PAUSED");
        await stopLocalCapture();
      } catch (pauseError) {
        queueCaptureFailure(pauseError);
      } finally {
        setBusy(false);
      }
    });
  }

  async function resume(target = displayedSession) {
    if (!target) return;
    setBusy(true);
    setError(null);
    let stream: MediaStream | null = null;
    try {
      stream = await acquireMicrophone();
      const updated =
        target.state === "PAUSED"
          ? await updateSessionAsync({
              sessionId: target.id,
              targetState: "RECORDING",
            })
          : target;
      await beginCapture(updated, stream);
    } catch (resumeError) {
      stream?.getTracks().forEach((track) => track.stop());
      setActiveSessionId(null);
      setError(
        resumeError instanceof Error
          ? resumeError.message
          : t("recording.errors.resume"),
      );
    } finally {
      setBusy(false);
    }
  }

  function finish(target = displayedSession) {
    if (!target) return;
    setBusy(true);
    setError(null);
    void runExclusive(async () => {
      try {
        let finalizing: RecordingSession;
        if (recorderRef.current?.state === "recording") {
          const segment = await takeSegment();
          finalizing = await appendSegment(segment, "FINALIZING");
        } else {
          finalizing = await updateSessionAsync({
            sessionId: target.id,
            targetState: "FINALIZING",
          });
        }
        await stopLocalCapture();
        await finishHandoff(finalizing);
      } catch (finishError) {
        queueCaptureFailure(finishError);
      } finally {
        setBusy(false);
      }
    });
  }

  async function abandon() {
    if (!recovery) return;
    setBusy(true);
    setError(null);
    try {
      await abandonSessionAsync(recovery.id);
      setActiveSessionId(null);
      setConfirmAbandon(false);
    } catch (abandonError) {
      setError(
        abandonError instanceof Error
          ? abandonError.message
          : t("recording.errors.abandon"),
      );
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (!sessionsQuery.error) return;
    setError(
      sessionsQuery.error instanceof Error
        ? sessionsQuery.error.message
        : t("recording.errors.recovery"),
    );
  }, [sessionsQuery.error, setError, t]);

  useEffect(() => {
    for (const finalizing of unfinishedSessions.filter(
      (item) => item.state === "FINALIZING" && item.id !== activeSessionId,
    )) {
      if (attemptedFinalizingRef.current.has(finalizing.id)) continue;
      attemptedFinalizingRef.current.add(finalizing.id);
      void finishHandoff(finalizing);
    }
  }, [activeSessionId, finishHandoff, unfinishedSessions]);

  useEffect(() => {
    return () => {
      useRecordingUiStore.getState().reset();
      void stopLocalCapture(false);
    };
  }, [stopLocalCapture]);

  useEffect(() => {
    if (displayedSession?.state !== "RECORDING") return;
    const update = () =>
      setElapsedMs(
        baseDurationRef.current +
          Math.max(0, performance.now() - segmentStartedAtRef.current),
      );
    update();
    const interval = window.setInterval(update, 1_000);
    return () => window.clearInterval(interval);
  }, [displayedSession?.state, setElapsedMs]);

  const recording = displayedSession?.state === "RECORDING";
  const paused = displayedSession?.state === "PAUSED";

  return (
    <>
      {!displayedSession && !recovery && !startOpen && error ? (
        <span
          role="alert"
          title={error}
          className="text-destructive text-label max-w-48 truncate px-1"
        >
          {error}
        </span>
      ) : null}
      {displayedSession ? (
        <div className="border-border bg-canvas flex min-w-0 items-center gap-1 rounded-lg border px-1 py-0.5">
          <span className="text-label text-ink-strong flex shrink-0 items-center gap-1 px-1">
            <span
              className={
                recording
                  ? "bg-destructive size-1.5 rounded-full"
                  : "bg-muted-foreground size-1.5 rounded-full"
              }
              aria-hidden="true"
            />
            <span className="max-compact:sr-only">
              {recording
                ? t("recording.statusRecording")
                : paused
                  ? t("recording.statusPaused")
                  : t("recording.statusFinalizing")}
            </span>
          </span>
          <span className="text-label text-ink-strong max-compact:sr-only max-w-40 truncate px-2">
            {displayedSession.title}
          </span>
          <span
            className="text-label text-ink-strong min-w-16 px-1 text-center font-medium tabular-nums"
            aria-label={t("recording.durationLabel")}
          >
            {formatDuration(elapsedMs)}
          </span>
          {error ? (
            <span
              role="alert"
              title={error}
              className="text-destructive text-label max-compact:max-w-24 max-w-48 truncate px-1"
            >
              {error}
            </span>
          ) : null}
          {recording ? (
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={handlePause}
              disabled={busy}
              aria-label={t("recording.pause")}
            >
              <Pause aria-hidden="true" />
            </Button>
          ) : paused ? (
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => void resume()}
              disabled={busy}
              aria-label={t("recording.resume")}
            >
              <Play aria-hidden="true" />
            </Button>
          ) : null}
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() =>
              void hideWindowTemporarily().catch((hideError: unknown) =>
                setError(
                  hideError instanceof Error
                    ? hideError.message
                    : t("recording.errors.hideWindow"),
                ),
              )
            }
            disabled={busy}
            aria-label={t("recording.hideWindow")}
          >
            <EyeOff aria-hidden="true" />
          </Button>
          <Button
            variant="destructive"
            size="icon-sm"
            onClick={() => finish()}
            disabled={busy}
            aria-label={
              displayedSession.state === "FINALIZING"
                ? t("recording.retryFinalize")
                : t("recording.finish")
            }
          >
            <CircleStop aria-hidden="true" />
          </Button>
        </div>
      ) : null}

      <Dialog
        open={startOpen}
        onOpenChange={(open) => !busy && setStartOpen(open)}
      >
        <DialogContent showCloseButton={!busy}>
          <form onSubmit={handleStart} className="flex flex-col gap-5">
            <DialogHeader>
              <DialogTitle>{t("recording.startTitle")}</DialogTitle>
              <DialogDescription>
                {t("recording.startDescription")}
              </DialogDescription>
            </DialogHeader>
            <Field>
              <FieldLabel htmlFor="recording-title">
                {t("recording.title")}
              </FieldLabel>
              <Input
                id="recording-title"
                value={title}
                maxLength={100}
                onChange={(event) => setTitle(event.target.value)}
                placeholder={t("recording.titlePlaceholder")}
                disabled={busy}
              />
              <FieldDescription>{t("recording.titleHint")}</FieldDescription>
            </Field>
            <Field>
              <FieldLabel htmlFor="recording-course">
                {t("recording.course")}
              </FieldLabel>
              <Select
                items={courseItems}
                value={courseId}
                onValueChange={(value) =>
                  setCourseId(value === "__none__" ? null : value)
                }
                disabled={busy || courses.isPending}
              >
                <SelectTrigger id="recording-course" className="w-full">
                  <SelectValue placeholder={t("recording.noCourse")}>
                    {courseId
                      ? (activeCourses.find((course) => course.id === courseId)
                          ?.name ?? null)
                      : t("recording.noCourse")}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    {courseItems.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
              {courses.isError ? (
                <FieldDescription>
                  {t("recording.courseError")}
                </FieldDescription>
              ) : null}
            </Field>
            {error ? (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            ) : null}
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setStartOpen(false)}
                disabled={busy}
              >
                {t("recording.cancel")}
              </Button>
              <Button type="submit" disabled={busy}>
                <Mic data-icon="inline-start" aria-hidden="true" />
                {busy ? t("recording.starting") : t("recording.start")}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(recovery)}>
        <DialogContent showCloseButton={false}>
          <DialogHeader>
            <DialogTitle>{t("recording.recoveryTitle")}</DialogTitle>
            <DialogDescription>
              {t("recording.recoveryDescription", {
                title: recovery?.title,
                duration: formatDuration(recovery?.recorded_duration_ms ?? 0),
              })}
            </DialogDescription>
          </DialogHeader>
          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}
          {confirmAbandon ? (
            <Alert variant="destructive">
              <AlertDescription>
                {t("recording.abandonWarning")}
              </AlertDescription>
            </Alert>
          ) : null}
          <DialogFooter className="sm:justify-between">
            {confirmAbandon ? (
              <>
                <Button
                  variant="outline"
                  onClick={() => setConfirmAbandon(false)}
                  disabled={busy}
                >
                  {t("recording.cancel")}
                </Button>
                <Button
                  variant="destructive"
                  onClick={() => void abandon()}
                  disabled={busy}
                >
                  {t("recording.confirmAbandon")}
                </Button>
              </>
            ) : (
              <>
                <Button
                  variant="destructive"
                  onClick={() => setConfirmAbandon(true)}
                  disabled={busy}
                >
                  {t("recording.abandon")}
                </Button>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    onClick={() => finish(recovery)}
                    disabled={busy}
                  >
                    {t("recording.finish")}
                  </Button>
                  <Button onClick={() => void resume(recovery)} disabled={busy}>
                    {t("recording.resume")}
                  </Button>
                </div>
              </>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
