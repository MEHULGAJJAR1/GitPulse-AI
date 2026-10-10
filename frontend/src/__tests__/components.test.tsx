import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Activity } from "lucide-react";
import { DataModeBanner } from "@/components/common/common";
import { KpiCard } from "@/components/common/KpiCard";
import { CorrelationTable, WeekdayHourHeatmap } from "@/components/charts/charts";

describe("data-mode labelling", () => {
  it("labels synthetic data explicitly and never as live", () => {
    render(<DataModeBanner mode={{ mode: "synthetic", github_repos: 0, synthetic_repos: 4 }} />);
    expect(screen.getByText(/Synthetic demo data/i)).toBeInTheDocument();
    expect(screen.getByText("DEMO · synthetic")).toBeInTheDocument();
    expect(screen.queryByText(/Live GitHub data/i)).not.toBeInTheDocument();
  });
  it("shows live GitHub wording only for live mode", () => {
    render(<DataModeBanner mode={{ mode: "live", github_repos: 2, synthetic_repos: 0 }} />);
    expect(screen.getByText(/Live GitHub data/i)).toBeInTheDocument();
    expect(screen.queryByText(/DEMO/)).not.toBeInTheDocument();
  });
  it("mixed mode keeps both sources visible", () => {
    render(<DataModeBanner mode={{ mode: "mixed", github_repos: 2, synthetic_repos: 4 }} />);
    expect(screen.getByText(/4 repositories are/)).toBeInTheDocument();
    expect(screen.getByText(/2 repo\(s\) are live GitHub data/)).toBeInTheDocument();
  });
});

describe("KpiCard", () => {
  it("renders label, value and hint", () => {
    render(<KpiCard label="Commits" value="391" hint="vs previous window" icon={Activity} delta={-9.5} />);
    expect(screen.getByText("Commits")).toBeInTheDocument();
    expect(screen.getByText("391")).toBeInTheDocument();
    expect(screen.getByText("vs previous window")).toBeInTheDocument();
  });
});

describe("heatmap and correlation", () => {
  it("draws a full 7x24 grid and shows zero for empty cells", () => {
    const { container } = render(<WeekdayHourHeatmap data={[{ weekday: 1, hour_utc: 9, commits: 12 }]} />);
    expect(container.querySelectorAll("[title*='UTC']")).toHaveLength(168);
    expect(container.querySelector("[title='Mon 9:00 UTC · 12 commit(s)']")).not.toBeNull();
    expect(container.querySelector("[title='Tue 0:00 UTC · 0 commit(s)']")).not.toBeNull();
  });
  it("shows the rho value and marks significance", () => {
    render(<CorrelationTable pairs={[{ metric_a: "commits", metric_b: "prs_merged", spearman_rho: 0.54, pearson_r: 0.58, strength: "moderate", significant: true }]} />);
    const row = screen.getByRole("row", { name: /commits/ });
    expect(within(row).getByText("0.54")).toBeInTheDocument();
    expect(within(row).getByText(/significant/)).toBeInTheDocument();
  });
});
