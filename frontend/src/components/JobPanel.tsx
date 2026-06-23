import type { Job } from "../types";

type JobPanelProps = {
  jobs: Job[];
  isLoading: boolean;
  error: string | null;
  onRefresh: () => void;
};

function JobPanel({ jobs, isLoading, error, onRefresh }: JobPanelProps) {
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
      {isLoading ? <p className="muted">Loading jobs...</p> : null}
      {!isLoading && jobs.length === 0 ? <p className="muted">No jobs yet.</p> : null}

      <div className="job-list">
        {jobs.map((job) => (
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
            {job.error_message ? <p className="error-message compact">{job.error_message}</p> : null}
          </article>
        ))}
      </div>
    </section>
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
