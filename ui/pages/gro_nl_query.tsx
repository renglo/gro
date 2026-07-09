import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Loader2, Sparkles, PlayCircle } from "lucide-react";

interface GroNlQueryProps {
  portfolio: string;
  org: string;
}

const SAMPLE_REQUEST =
  "Find subnet nodes connected to vpc nodes using infrastructure links, return the subnet side, limit 50.";

function extractErrorMessage(body: Record<string, unknown>): string {
  const output = body?.output;
  if (typeof output === "string") {
    return output;
  }
  if (Array.isArray(output) && output.length > 0) {
    const first = output[0];
    if (typeof first === "object" && first && "message" in first) {
      return String((first as Record<string, unknown>).message);
    }
  }
  if (typeof output === "object" && output && "message" in output) {
    return String((output as Record<string, unknown>).message);
  }
  return String(body?.message || "Request failed");
}

function unwrapHandlerOutput(body: Record<string, unknown>): Record<string, unknown> {
  const output = body?.output;
  if (typeof output === "object" && output && !Array.isArray(output)) {
    return output as Record<string, unknown>;
  }
  if (Array.isArray(output) && output.length > 0 && typeof output[0] === "object" && output[0]) {
    return output[0] as Record<string, unknown>;
  }
  return body;
}

function getQueryV1FromTranslatorOutput(output: Record<string, unknown>): Record<string, unknown> | null {
  const direct = output.query_v1;
  if (direct && typeof direct === "object" && !Array.isArray(direct)) {
    return direct as Record<string, unknown>;
  }
  const nested = output.output;
  if (nested && typeof nested === "object" && !Array.isArray(nested)) {
    const nestedQuery = (nested as Record<string, unknown>).query_v1;
    if (nestedQuery && typeof nestedQuery === "object" && !Array.isArray(nestedQuery)) {
      return nestedQuery as Record<string, unknown>;
    }
  }
  return null;
}

export default function GroNlQuery({ portfolio, org }: GroNlQueryProps) {
  const [requestText, setRequestText] = useState(SAMPLE_REQUEST);
  const [generatedQueryRaw, setGeneratedQueryRaw] = useState("");
  const [translateResponse, setTranslateResponse] = useState<unknown>(null);
  const [executeResponse, setExecuteResponse] = useState<unknown>(null);
  const [translating, setTranslating] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [error, setError] = useState("");

  const endpoint = (handler: string) =>
    `${import.meta.env.VITE_API_URL}/_schd/${portfolio}/${org}/call/gro/${handler}`;

  const translateToGroQuery = async () => {
    setError("");
    setExecuteResponse(null);
    setTranslating(true);
    try {
      const response = await fetch(endpoint("natural_language_query"), {
        method: "POST",
        headers: {
          Authorization: `Bearer ${sessionStorage.accessToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          portfolio,
          org,
          request_text: requestText,
        }),
      });
      const body = await response.json();
      if (!response.ok || !body?.success) {
        setError(extractErrorMessage(body));
        setTranslateResponse(body);
        return;
      }

      const output = unwrapHandlerOutput(body);
      setTranslateResponse(output);
      const queryV1 = getQueryV1FromTranslatorOutput(output);
      if (!queryV1) {
        setError("Translator returned no query_v1 payload");
        return;
      }
      setGeneratedQueryRaw(JSON.stringify(queryV1, null, 2));
    } catch (err: any) {
      setError(err?.message || "Unexpected error generating query");
    } finally {
      setTranslating(false);
    }
  };

  const executeQuery = async () => {
    setError("");
    setExecuting(true);
    setExecuteResponse(null);
    let queryPayload: Record<string, unknown>;
    try {
      queryPayload = JSON.parse(generatedQueryRaw);
    } catch {
      setError("Generated query JSON is invalid");
      setExecuting(false);
      return;
    }

    try {
      const response = await fetch(endpoint("execute_plan"), {
        method: "POST",
        headers: {
          Authorization: `Bearer ${sessionStorage.accessToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          ...queryPayload,
          portfolio,
          org,
        }),
      });
      const body = await response.json();
      if (!response.ok || !body?.success) {
        setError(extractErrorMessage(body));
        setExecuteResponse(body);
        return;
      }
      setExecuteResponse(body?.output ?? body);
    } catch (err: any) {
      setError(err?.message || "Unexpected error executing query");
    } finally {
      setExecuting(false);
    }
  };

  return (
    <Card className="mx-auto w-full overflow-hidden sm:w-11/12">
      <CardHeader>
        <CardTitle>Gro Natural Language Query Lab</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4">
        <div className="text-xs text-muted-foreground">
          Enter an English request, generate a Gro Query v1 JSON payload with the LLM, then execute it.
        </div>

        <Textarea
          id="nl-request"
          className="min-h-[140px]"
          value={requestText}
          onChange={(e) => setRequestText(e.target.value)}
          placeholder="Describe what you want to query..."
        />

        <div className="flex flex-wrap gap-2">
          <Button onClick={translateToGroQuery} disabled={translating || !requestText.trim()}>
            {translating ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Sparkles className="mr-2 h-4 w-4" />}
            Generate Gro Query
          </Button>
          <Button variant="secondary" onClick={executeQuery} disabled={executing || !generatedQueryRaw.trim()}>
            {executing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <PlayCircle className="mr-2 h-4 w-4" />}
            Execute Query
          </Button>
        </div>

        {error && <div className="text-sm text-red-600">{error}</div>}

        {generatedQueryRaw && (
          <div className="grid gap-2">
            <Textarea
              id="gro-query"
              className="min-h-[260px] font-mono text-xs"
              value={generatedQueryRaw}
              onChange={(e) => setGeneratedQueryRaw(e.target.value)}
            />
          </div>
        )}

        {(translateResponse || executeResponse) && (
          <div className="grid gap-4 md:grid-cols-2">
            {translateResponse && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">Translator response</CardTitle>
                </CardHeader>
                <CardContent>
                  <pre className="max-h-[360px] overflow-auto rounded bg-muted p-3 text-xs">
                    {JSON.stringify(translateResponse, null, 2)}
                  </pre>
                </CardContent>
              </Card>
            )}
            {executeResponse && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">Execution response</CardTitle>
                </CardHeader>
                <CardContent>
                  <pre className="max-h-[360px] overflow-auto rounded bg-muted p-3 text-xs">
                    {JSON.stringify(executeResponse, null, 2)}
                  </pre>
                </CardContent>
              </Card>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
