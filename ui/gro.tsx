import { useEffect } from "react";
import ToolDataCRUD from "@renglo/data/pages/tool_data_crud";
import GroPipelineProbe from "./pages/gro_pipeline_probe";
import GroExecutorProbe from "./pages/gro_executor_probe";

interface Portfolio {
  name: string;
  portfolio_id: string;
  orgs: Record<string, Org>;
  tools: Record<string, Tool>;
}

interface Org {
  name: string;
  org_id: string;
  tools: string[];
}

interface Tool {
  name: string;
  handle: string;
}

export default function Gro({
  portfolio,
  org,
  tool,
  section,
}: {
  portfolio: string;
  org: string;
  tool: string;
  section?: string;
  tree?: { portfolios: Record<string, Portfolio> };
  query?: Record<string, string>;
}) {
  useEffect(() => {
    if (!section) {
      window.location.href = `/${portfolio}/${org}/${tool}/pipeline`;
    }
  }, [section, portfolio, org, tool]);

  if (!section) {
    return null;
  }

  return (
    <div className="flex min-h-screen w-full flex-col bg-muted/40">
      <div className="flex flex-col sm:gap-2 sm:pl-2">
        {section === "pipeline" && <GroPipelineProbe portfolio={portfolio} org={org} tool={tool} />}
        {section === "executor" && <GroExecutorProbe portfolio={portfolio} org={org} tool={tool} />}

        {section === "gro_node_counts" && (
          <ToolDataCRUD readonly={true} portfolio={portfolio} org={org} tool={tool} ring={section} />
        )}
        {section === "gro_property_cardinality" && (
          <ToolDataCRUD readonly={true} portfolio={portfolio} org={org} tool={tool} ring={section} />
        )}
        {section === "gro_edge_fanout" && (
          <ToolDataCRUD readonly={true} portfolio={portfolio} org={org} tool={tool} ring={section} />
        )}
      </div>
    </div>
  );
}
