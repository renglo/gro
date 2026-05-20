import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Loader2 } from "lucide-react";

interface GroExecutorProbeProps {
  portfolio: string;
  org: string;
  tool: string;
}

const SAMPLE_PAYLOAD = {
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

export default function GroExecutorProbe({ portfolio, org }: GroExecutorProbeProps) {
  const [payloadRaw, setPayloadRaw] = useState(JSON.stringify(SAMPLE_PAYLOAD, null, 2));
  const [running, setRunning] = useState(false);
  const [response, setResponse] = useState<any>(null);
  const [error, setError] = useState<string>("");

  const runExecutor = async () => {
    setError("");
    setResponse(null);
    let payload: any;
    try {
      payload = JSON.parse(payloadRaw);
    } catch {
      setError("Invalid JSON payload");
      return;
    }

    payload.portfolio = portfolio;
    payload.org = org;

    setRunning(true);
    try {
      const apiResponse = await fetch(`${import.meta.env.VITE_API_URL}/_schd/${portfolio}/${org}/call/gro/execute_plan`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${sessionStorage.accessToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });
      const body = await apiResponse.json();
      if (!apiResponse.ok || !body?.success) {
        setError(body?.message || body?.output || "Execution failed");
        return;
      }
      setResponse(body?.output ?? body);
    } catch (err: any) {
      setError(err?.message || "Unexpected error executing plan");
    } finally {
      setRunning(false);
    }
  };

  return (
    <Card className="mx-auto w-full sm:w-11/12 overflow-hidden">
      <CardHeader>
        <CardTitle>Gro Execute Plan (Default/Reference Executor)</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4">
        <div className="text-xs text-muted-foreground">
          Request body with top-level <code>query_pattern</code> (plan-and-execute) or <code>execution_plan</code> (execute only).
          <code>portfolio</code> and <code>org</code> are taken from the URL.
        </div>

        <Textarea
          className="min-h-[260px] font-mono text-xs"
          value={payloadRaw}
          onChange={(e) => setPayloadRaw(e.target.value)}
        />

        <div className="flex gap-2">
          <Button onClick={runExecutor} disabled={running}>
            {running ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            Run Executor
          </Button>
        </div>

        {error && <div className="text-sm text-red-600">{error}</div>}

        {response && (
          <pre className="bg-muted p-3 rounded text-xs overflow-auto max-h-[420px]">
{JSON.stringify(response, null, 2)}
          </pre>
        )}
      </CardContent>
    </Card>
  );
}
