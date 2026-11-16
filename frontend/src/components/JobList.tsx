import type { JobResult, JobStateMap } from "../types/job";
import { JobCard } from "./JobCard";

interface Props {
  jobs: JobResult[];
  jobStates: JobStateMap;
  onSave: (url: string) => void;
  onIgnore: (url: string) => void;
  onOpenDetails: (job: JobResult) => void;
}

export function JobList({ jobs, jobStates, onSave, onIgnore, onOpenDetails }: Props) {
  if (jobs.length === 0) {
    return (
      <div
        data-testid="empty-results"
        className="card px-6 py-14 text-center"
      >
        <p className="text-[17px] font-semibold text-ink">Nothing matches these filters.</p>
        <p className="caption mt-1 text-faint">
          Lower the minimum score or clear the company filter to see more.
        </p>
      </div>
    );
  }

  return (
    <div className="grid gap-4">
      {jobs.map((job, index) => (
        <div
          key={job.job_url}
          className="rise min-w-0"
          // A long list lands as one block otherwise; a short stagger lets
          // the eye follow it down. Capped so job 40 is not a second late.
          style={{ animationDelay: `${Math.min(index, 8) * 35}ms` }}
        >
          <JobCard
            job={job}
            state={jobStates[job.job_url]}
            onSave={() => onSave(job.job_url)}
            onIgnore={() => onIgnore(job.job_url)}
            onOpenDetails={() => onOpenDetails(job)}
          />
        </div>
      ))}
    </div>
  );
}
