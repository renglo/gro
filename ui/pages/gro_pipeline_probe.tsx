import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { CheckCircle2, Circle, Loader2 } from "lucide-react";

interface GroPipelineProbeProps {
  portfolio: string;
  org: string;
  tool: string;
}

type StageKey =
  | "query_parser"
  | "constraint_extractor"
  | "graph_statistics_registry"
  | "candidate_plan_generator"
  | "cost_estimator"
  | "plan_ranker"
  | "execution_plan_builder";

const STAGES: { key: StageKey; label: string; hint: string }[] = [
  { key: "query_parser", label: "Query Parser", hint: "Normalize query pattern" },
  { key: "constraint_extractor", label: "Constraint Extractor", hint: "Extract anchors and filters" },
  { key: "graph_statistics_registry", label: "Graph Statistics Registry", hint: "Compute and persist stats" },
  { key: "candidate_plan_generator", label: "Candidate Plan Generator", hint: "Generate plan alternatives" },
  { key: "cost_estimator", label: "Cost Estimator", hint: "Estimate cost per plan" },
  { key: "plan_ranker", label: "Plan Ranker", hint: "Select best plan" },
  { key: "execution_plan_builder", label: "Execution Plan Builder", hint: "Build executable operations list" },
];

const SAMPLE_QUERY_PATTERN = {
  target: "Hotel",
  constraints: [
    { node: "City", property: "name", operator: "=", value: "Rio" },
    { node: "Review", property: "stars", operator: "=", value: 5 },
  ],
  relationships: [
    { from: "Hotel", edge: "LOCATED_IN", to: "City" },
    { from: "Review", edge: "REVIEWS", to: "Hotel" },
  ],
};

export default function GroPipelineProbe({ portfolio, org }: GroPipelineProbeProps) {
  const [queryPatternRaw, setQueryPatternRaw] = useState(JSON.stringify(SAMPLE_QUERY_PATTERN, null, 2));
  const [currentStage, setCurrentStage] = useState(0);
  const [running, setRunning] = useState<StageKey | null>(null);
  const [error, setError] = useState<string>("");
  const [stageOutputs, setStageOutputs] = useState<Record<string, any>>({});

  const parsedQueryPattern = useMemo(() => {
    try {
      return JSON.parse(queryPatternRaw);
    } catch {
      return null;
    }
  }, [queryPatternRaw]);

  const endpoint = (handler: string) => `${import.meta.env.VITE_API_URL}/_schd/${portfolio}/${org}/call/gro/${handler}`;

  const buildPayloadForStage = (key: StageKey): Record<string, any> => {
    const parserOut = stageOutputs.query_parser;
    const extractorOut = stageOutputs.constraint_extractor;
    const statsOut = stageOutputs.graph_statistics_registry;
    const generatorOut = stageOutputs.candidate_plan_generator;
    const estimatorOut = stageOutputs.cost_estimator;
    const rankerOut = stageOutputs.plan_ranker;

    const base = {
      portfolio,
      org,
      query_pattern: parserOut?.query_pattern || parsedQueryPattern,
    };

    switch (key) {
      case "query_parser":
        return {
          portfolio,
          org,
          query_pattern: parsedQueryPattern,
        };
      case "constraint_extractor":
        return base;
      case "graph_statistics_registry":
        return base;
      case "candidate_plan_generator":
        return {
          ...base,
          anchors: extractorOut?.anchors || [],
        };
      case "cost_estimator":
        return {
          ...base,
          candidate_plans: generatorOut?.candidate_plans || [],
          stats: statsOut?.stats || {},
        };
      case "plan_ranker":
        return {
          ...base,
          estimated_plans: estimatorOut?.estimated_plans || [],
        };
      case "execution_plan_builder":
        return {
          ...base,
          best_plan: rankerOut?.best_plan || {},
        };
      default:
        return base;
    }
  };

  const runStage = async (index: number, moveNext = false) => {
    const stage = STAGES[index];
    if (!stage) {
      return;
    }
    if (!parsedQueryPattern) {
      setError("Invalid JSON in Query Pattern");
      return;
    }

    setError("");
    setRunning(stage.key);

    try {
      const payload = buildPayloadForStage(stage.key);
      const response = await fetch(endpoint(stage.key), {
        method: "POST",
        headers: {
          Authorization: `Bearer ${sessionStorage.accessToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      const body = await response.json();
      if (!response.ok || !body?.success) {
        setError(body?.message || body?.output || "Stage execution failed");
        return;
      }

      const output = body?.output ?? body;
      setStageOutputs((prev) => ({
        ...prev,
        [stage.key]: output,
      }));
      if (moveNext && index < STAGES.length - 1) {
        setCurrentStage(index + 1);
      }
    } catch (err: any) {
      setError(err?.message || "Unexpected error running stage");
    } finally {
      setRunning(null);
    }
  };

  const resetPipeline = () => {
    setStageOutputs({});
    setCurrentStage(0);
    setError("");
  };

  return (
    <Card className="mx-auto w-full sm:w-11/12 overflow-hidden flex flex-col h-[calc(100vh-8rem)]">
      <CardHeader>
        <CardTitle>Gro Pipeline Troubleshooting</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-6 flex-1 overflow-y-auto pr-2">
        <div className="grid gap-2">
          <div className="text-sm font-medium">Query Pattern Input</div>
          <Textarea
            className="min-h-[220px] font-mono text-xs"
            value={queryPatternRaw}
            onChange={(e) => setQueryPatternRaw(e.target.value)}
          />
          <div className="text-xs text-muted-foreground">
            The UI orchestrates the pipeline by running one handler at a time. Use <b>Next</b> to continue.
          </div>
        </div>

        <div className="grid gap-3">
          {STAGES.map((stage, idx) => {
            const done = !!stageOutputs[stage.key];
            const isCurrent = idx === currentStage;
            const isRunning = running === stage.key;
            return (
              <Card key={stage.key} className={isCurrent ? "border-primary" : ""}>
                <CardContent className="pt-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-start gap-2">
                      {done ? <CheckCircle2 className="h-4 w-4 mt-1 text-green-600" /> : <Circle className="h-4 w-4 mt-1" />}
                      <div>
                        <div className="text-sm font-medium">{idx + 1}. {stage.label}</div>
                        <div className="text-xs text-muted-foreground">{stage.hint}</div>
                      </div>
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={!!running}
                      onClick={() => runStage(idx, false)}
                    >
                      {isRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : "Run"}
                    </Button>
                  </div>

                  {done && (
                    <pre className="mt-3 bg-muted p-3 rounded text-xs overflow-auto max-h-[220px]">
{JSON.stringify(stageOutputs[stage.key], null, 2)}
                    </pre>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>

        {error && <div className="text-sm text-red-600">{error}</div>}

        <div className="flex gap-2">
          <Button
            onClick={() => runStage(currentStage, true)}
            disabled={!!running || currentStage >= STAGES.length}
          >
            {running ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            Next
          </Button>
          <Button
            variant="secondary"
            onClick={resetPipeline}
            disabled={!!running}
          >
            Reset
          </Button>
          <Button
            variant="outline"
            onClick={() => runStage(STAGES.length - 1, false)}
            disabled={!!running}
          >
            Run Final Builder
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
