import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { ReactNode } from "react";
import {
  PlayCircle,
  Workflow,
  Database,
  Sigma,
  Link2,
  BarChart3,
  Sparkles,
  Shield,
} from "lucide-react";

interface ToolMenuProps {
  portfolio: string;
  org: string;
  tool?: string;
  section?: string;
  onNavigate: (path: string) => void;
}

function NavIcon({
  active,
  label,
  onClick,
  children,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="flex items-center flex-col">
            <button
              onClick={onClick}
              className={
                active
                  ? "group flex h-9 w-9 shrink-0 items-center justify-center gap-2 rounded-full bg-gray-200 text-lg font-semibold text-muted-foreground md:h-12 md:w-12 md:text-base"
                  : "flex h-9 w-9 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:text-foreground md:h-8 md:w-8"
              }
            >
              {children}
              <span className="sr-only">{label}</span>
            </button>
            <span className="text-xxs">{label}</span>
          </div>
        </TooltipTrigger>
        <TooltipContent side="right">{label}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

export default function ToolGroSideNav({ portfolio, org, tool, section, onNavigate }: ToolMenuProps) {
  if (!org || org === "settings") {
    return null;
  }

  return (
    <nav className="flex flex-col items-center gap-2 px-1 sm:py-4">
      <NavIcon
        active={section === "pipeline"}
        label="Pipeline"
        onClick={() => onNavigate(`/${portfolio}/${org}/${tool}/pipeline`)}
      >
        <Workflow className="h-5 w-5" />
      </NavIcon>

      <NavIcon
        active={section === "executor"}
        label="Executor"
        onClick={() => onNavigate(`/${portfolio}/${org}/${tool}/executor`)}
      >
        <PlayCircle className="h-5 w-5" />
      </NavIcon>

      <NavIcon
        active={section === "nl_query"}
        label="NL Query"
        onClick={() => onNavigate(`/${portfolio}/${org}/${tool}/nl_query`)}
      >
        <Sparkles className="h-5 w-5" />
      </NavIcon>

      <NavIcon
        active={section === "cypher_catalog"}
        label="Cypher"
        onClick={() => onNavigate(`/${portfolio}/${org}/${tool}/cypher_catalog`)}
      >
        <Shield className="h-5 w-5" />
      </NavIcon>

      <NavIcon
        active={section === "statistics"}
        label="Stats"
        onClick={() => onNavigate(`/${portfolio}/${org}/${tool}/statistics`)}
      >
        <BarChart3 className="h-5 w-5" />
      </NavIcon>

      <NavIcon
        active={section === "gro_node_counts"}
        label="Nodes"
        onClick={() => onNavigate(`/${portfolio}/${org}/${tool}/gro_node_counts`)}
      >
        <Database className="h-5 w-5" />
      </NavIcon>

      <NavIcon
        active={section === "gro_property_cardinality"}
        label="Properties"
        onClick={() => onNavigate(`/${portfolio}/${org}/${tool}/gro_property_cardinality`)}
      >
        <Sigma className="h-5 w-5" />
      </NavIcon>

      <NavIcon
        active={section === "gro_edge_fanout"}
        label="FanOut"
        onClick={() => onNavigate(`/${portfolio}/${org}/${tool}/gro_edge_fanout`)}
      >
        <Link2 className="h-5 w-5" />
      </NavIcon>
    </nav>
  );
}
