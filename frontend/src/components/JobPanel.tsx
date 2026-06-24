import { useState } from "react";

import { fetchJobSteps, retryFailedJobSteps } from "../api";
import type { Job, JobStep } from "../types";

type JobPanelProps = {
  jobs: Job[];
  isLoading: boolean;
  error: string | null;
  onRefresh: () => Promise<void> | void;
};

function JobPanel({ jobs, isLoading, error, onRefresh }: JobPanelProps) {
  const [expandedJobId, setExpandedJobId] = useState<number | null>(null);
  const [stepsByJobId, setStepsByJobId] = useState<Record<number, JobStep[]>>({});
  const [loadingStepsJobId, setLoadingStepsJobId] = useState<number | null>(null);
  const [retryingJobId, setRetryingJobId] = useState<number | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  async function toggleJob(job: Job) {
    if (expandedJobId === job.id) {
      setExpandedJobId(null);
      return;
    }

    setExpandedJobId(job.id);
    setDetailError(null);
    if (stepsByJobId[job.id]) {
      return;
    }

    setLoadingStepsJobId(job.id);
    try {
      const steps = await fetchJobSteps(job.id);
      setStepsByJobId((current) => ({ ...current, [job.id]: steps }));
    } catch (jobError) {
      setDetailError(jobError instanceof Error ? jobError.message : "Unable to load job steps.");
    } finally {
      setLoadingStepsJobId(null);
    }
  }

  async function handleRetry(job: Job) {
    setRetryingJobId(job.id);
    setDetailError(null);
    try {
      const retriedJob = await retryFailedJobSteps(job.id);
      setExpandedJobId(job.id);
      setStepsByJobId((current) => ({ ...current, [job.id]: retriedJob.steps }));
      await onRefresh();
    } catch (jobError) {
      setDetailError(jobError instanceof Error ? jobError.message : "Unable to retry failed steps.");
    } finally {
      setRetryingJobId(null);
    }
  }

  return (
    <section className="panel job-panel" aria-labelledby="jobs-heading">
      <div className="panel-header">
        <div>
          <p className="panel-kicker">Jobs</p>
          <h2 id="jobs-heading">Processing</h2>
        </div>
        <button className="secondary-button" type="button" onClick={onRefresh} disabled={isLoading}>
          Refresh
        </button>
      </div>

      {error ? <p className="error-message">{error}</p> : null}
      {detailError ? <p className="error-message">{detailError}</p> : null}
      {isLoading ? <p className="muted">Loading jobs...</p> : null}
      {!isLoading && jobs.length === 0 ? (
        <p className="muted">No processing jobs yet. Upload a document, then generate summaries to create one.</p>
      ) : null}

      <div className="job-list">
        {jobs.map((job) => {
          const isExpanded = expandedJobId === job.id;
          const steps = stepsByJobId[job.id] ?? job.steps;
          return (
            <article className="job-row" key={job.id}>
              <div className="job-row-header">
                <strong>Job {job.id}</strong>
                <span className={`status-pill ${job.status}`}>{job.status}</span>
              </div>
              <dl className="job-details">
                <div>
                  <dt>type</dt>
                  <dd>{job.job_type}</dd>
                </div>
                <div>
                  <dt>document</dt>
                  <dd>ID {job.document_id}</dd>
                </div>
                <div>
                  <dt>progress</dt>
                  <dd>
                    {job.completed_steps}/{job.total_steps}
                    {job.failed_steps ? `, ${job.failed_steps} failed` : ""}
                  </dd>
                </div>
                <div>
                  <dt>finished</dt>
                  <dd>{job.finished_at ? formatDate(job.finished_at) : "not finished"}</dd>
                </div>
              </dl>
              <div className="job-actions">
                <button className="secondary-button" type="button" onClick={() => void toggleJob(job)}>
                  {isExpanded ? "Hide steps" : "Show steps"}
                </button>
                {job.failed_steps > 0 ? (
                  <button
                    className="secondary-button"
                    type="button"
                    onClick={() => void handleRetry(job)}
                    disabled={retryingJobId === job.id}
                  >
                    {retryingJobId === job.id ? "Retrying" : "Retry failed"}
                  </button>
                ) : null}
              </div>
              {job.error_message ? <p className="error-message compact">{job.error_message}</p> : null}
              {isExpanded ? (
                <JobSteps steps={steps} isLoading={loadingStepsJobId === job.id} />
              ) : null}
            </article>
          );
        })}
      </div>
    </section>
  );
}

type JobStepsProps = {
  steps: JobStep[];
  isLoading: boolean;
};

function JobSteps({ steps, isLoading }: JobStepsProps) {
  if (isLoading) {
    return <p className="inline-note">Loading steps...</p>;
  }
  if (steps.length === 0) {
    return <p className="inline-note">No step records for this job.</p>;
  }

  return (
    <div className="job-steps">
      {steps.map((step) => (
        <div className="job-step" key={step.id}>
          <div className="job-row-header">
            <strong>{step.step_type}</strong>
            <span className={`status-pill ${step.status}`}>{step.status}</span>
          </div>
          <dl className="job-details">
            <div>
              <dt>target</dt>
              <dd>{step.target_stable_id ?? `${step.target_type} ${step.target_id}`}</dd>
            </div>
            <div>
              <dt>attempts</dt>
              <dd>{step.attempt_count}</dd>
            </div>
            <div>
              <dt>finished</dt>
              <dd>{step.finished_at ? formatDate(step.finished_at) : "not finished"}</dd>
            </div>
          </dl>
          {step.error_message ? <p className="error-message compact">{step.error_message}</p> : null}
        </div>
      ))}
    </div>
  );
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export default JobPanel;
