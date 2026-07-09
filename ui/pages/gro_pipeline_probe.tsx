import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { CheckCircle2, Circle, Loader2, XCircle } from "lucide-react";

interface GroPipelineProbeProps {
  portfolio: string;
  org: string;
  tool: string;
}

type StageKey =
  | "query_parser"
  | "constraint_extractor"
  | "candidate_plan_generator"
  | "cost_estimator"
  | "plan_ranker"
  | "execution_plan_builder";

const STAGES: { key: StageKey; label: string; hint: string }[] = [
  { key: "query_parser", label: "Query Parser", hint: "Normalize query pattern" },
  { key: "constraint_extractor", label: "Constraint Extractor", hint: "Extract anchors and filters" },
  { key: "candidate_plan_generator", label: "Candidate Plan Generator", hint: "Generate plan alternatives" },
  { key: "cost_estimator", label: "Cost Estimator", hint: "Estimate cost per plan (reads persisted stats)" },
  { key: "plan_ranker", label: "Plan Ranker", hint: "Select best plan" },
  { key: "execution_plan_builder", label: "Execution Plan Builder", hint: "Build executable operations list" },
];

const SAMPLE_REQUEST_BODY = {
  query_pattern: {
    target: "Hotel",
    constraints: [
      { node: "City", property: "name", operator: "=", value: "Rio" },
      { node: "Review", property: "stars", operator: "=", value: 5 },
    ],
    relationships: [
      { from: "Hotel", edge: "LOCATED_IN", to: "City" },
      { from: "Review", edge: "REVIEWS", to: "Hotel" },
    ],
  },
};

export default function GroPipelineProbe({ portfolio, org }: GroPipelineProbeProps) {
  const [queryPatternRaw, setQueryPatternRaw] = useState(JSON.stringify(SAMPLE_REQUEST_BODY, null, 2));
  const [currentStage, setCurrentStage] = useState(0);
  const [running, setRunning] = useState<StageKey | null>(null);
  const [error, setError] = useState<string>("");
  const [stageOutputs, setStageOutputs] = useState<Record<string, any>>({});

  const parsedRequestBody = useMemo(() => {
    try {
      const body = JSON.parse(queryPatternRaw);
      if (!body || typeof body !== "object" || Array.isArray(body)) {
        return null;
      }
      const pattern = (body as Record<string, unknown>).query_pattern;
      if (!pattern || typeof pattern !== "object" || Array.isArray(pattern)) {
        return null;
      }
      return { body: body as Record<string, unknown>, query_pattern: pattern as Record<string, unknown> };
    } catch {
      return null;
    }
  }, [queryPatternRaw]);

  const endpoint = (handler: string) => `${import.meta.env.VITE_API_URL}/_schd/${portfolio}/${org}/call/gro/${handler}`;

  const buildPayloadForStage = (key: StageKey): Record<string, any> => {
    const parserOut = stageOutputs.query_parser;
    const extractorOut = stageOutputs.constraint_extractor;
    const generatorOut = stageOutputs.candidate_plan_generator;
    const estimatorOut = stageOutputs.cost_estimator;
    const rankerOut = stageOutputs.plan_ranker;

    const base = {
      portfolio,
      org,
      query_pattern: parserOut?.query_pattern || parsedRequestBody?.query_pattern,
    };

    switch (key) {
      case "query_parser":
        return {
          portfolio,
          org,
          query_pattern: parsedRequestBody?.query_pattern,
        };
      case "constraint_extractor":
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
    if (!parsedRequestBody) {
      setError('Invalid JSON. Body must be an object with a "query_pattern" field.');
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
        const output = body?.output;
        let message = body?.message || "Stage execution failed";
        let stageOutput: Record<string, unknown> = {
          success: false,
          component: stage.key,
          message,
        };

        if (Array.isArray(output) && output.length > 0) {
          const first = output[0];
          if (typeof first === "object" && first && "message" in first) {
            message = String(first.message);
            stageOutput = first as Record<string, unknown>;
          } else {
            message = output
              .map((item) => (typeof item === "string" ? item : JSON.stringify(item)))
              .join("; ");
            stageOutput = { success: false, component: stage.key, message };
          }
        } else if (typeof output === "object" && output && !Array.isArray(output) && "message" in output) {
          message = String(output.message);
          stageOutput = output as Record<string, unknown>;
        } else if (typeof output === "string") {
          message = output;
          stageOutput = { success: false, component: stage.key, message: output };
        }

        setError(message);
        setStageOutputs((prev) => ({
          ...prev,
          [stage.key]: stageOutput,
        }));
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
          <div className="text-sm font-medium">Request body (JSON)</div>
          <Textarea
            className="min-h-[220px] font-mono text-xs"
            value={queryPatternRaw}
            onChange={(e) => setQueryPatternRaw(e.target.value)}
          />
          <div className="text-xs text-muted-foreground">
            Paste a scheduler request body with a top-level <code>query_pattern</code> (same shape as the query catalog).
            <code>portfolio</code> and <code>org</code> come from the URL. Use <b>Next</b> to run stages in order.
          </div>
        </div>

        <div className="grid gap-3">
          {STAGES.map((stage, idx) => {
            const stageOutput = stageOutputs[stage.key];
            const hasOutput = !!stageOutput;
            const failed = hasOutput && stageOutput?.success === false;
            const succeeded = hasOutput && !failed;
            const isCurrent = idx === currentStage;
            const isRunning = running === stage.key;
            return (
              <Card key={stage.key} className={isCurrent ? "border-primary" : ""}>
                <CardContent className="pt-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-start gap-2">
                      {failed ? (
                        <XCircle className="h-4 w-4 mt-1 text-red-600" />
                      ) : succeeded ? (
                        <CheckCircle2 className="h-4 w-4 mt-1 text-green-600" />
                      ) : (
                        <Circle className="h-4 w-4 mt-1" />
                      )}
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

                  {hasOutput && (
                    <pre className="mt-3 bg-muted p-3 rounded text-xs overflow-auto max-h-[220px]">
{JSON.stringify(stageOutput, null, 2)}
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
