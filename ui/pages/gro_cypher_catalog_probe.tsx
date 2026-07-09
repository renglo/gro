import { useCallback, useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Loader2, PlayCircle, ListChecks, RotateCcw, Search, Database } from "lucide-react";
import catalog from "../data/cybersecurity_query_catalog.json";
import ontologyTypes from "../data/aws_universal_types.json";

interface GroCypherCatalogProbeProps {
  portfolio: string;
  org: string;
}

type CatalogSection = "security" | "blast_radius";
type RunStatus = "idle" | "running" | "success" | "error";
type InspectPresetId = "overview" | "iam_grants" | "functions" | "dns_public";

interface CatalogQuery {
  id: string;
  section: CatalogSection;
  number: number;
  title: string;
  description: string;
  query: string;
  params: string[];
  default_params: Record<string, string | number>;
}

interface QueryRunResult {
  status: RunStatus;
  request: Record<string, unknown>;
  response: unknown;
  error: string;
  durationMs: number;
  rowCount: number | null;
  finishedAt: string;
}

interface InspectSummary {
  total_nodes: number;
  total_edges: number;
  nodes_by_universal_type: Record<string, number>;
  edges_by_relationship_type: Record<string, number>;
  provider_types_seen: Record<string, number>;
  unmapped_provider_types: string[];
}

interface SelectOption {
  value: string;
  label: string;
  count?: number;
}

const QUERIES = catalog as CatalogQuery[];
const ALL_VALUE = "__all__";
const DEFAULT_EDGE_TYPES = ["infrastructure_elements:links:infrastructure_elements:_id"];

const FALLBACK_UNIVERSAL_TYPES = Array.from(
  new Set(
    (ontologyTypes.type_mappings ?? []).map((item: { universal_type: string }) => item.universal_type),
  ),
).sort();

const FALLBACK_PROVIDER_TYPES = (ontologyTypes.type_mappings ?? [])
  .map((item: { provider_type: string; universal_type: string }) => ({
    value: item.provider_type,
    label: `${item.provider_type} → ${item.universal_type}`,
  }))
  .sort((a, b) => a.value.localeCompare(b.value));

const FALLBACK_RELATIONSHIPS = Array.from(
  new Set([
    "GRANTS",
    "HAS_POLICY",
    "ROUTES_TO",
    "ASSUMES",
    "READS",
    "WRITES",
    "INVOKES",
    "PROTECTED_BY",
    "DEPLOYED_IN",
    "MEMBER_OF",
    ...Object.keys(ontologyTypes.relationship_aliases ?? {}),
    ...Object.values(ontologyTypes.relationship_aliases ?? {}),
  ]),
).sort();

const INSPECT_PRESETS: Record<
  InspectPresetId,
  { label: string; description: string; filters: Record<string, string> }
> = {
  overview: {
    label: "Overview (recommended)",
    description: "No filters — sample nodes and edges from the loaded snapshot.",
    filters: {},
  },
  iam_grants: {
    label: "IAM grants",
    description: "Edges with GRANTS relationship type.",
    filters: { relationship_type: "GRANTS" },
  },
  functions: {
    label: "Lambda functions",
    description: "Nodes mapped to universal type Function.",
    filters: { universal_type: "Function" },
  },
  dns_public: {
    label: "DNS records",
    description: "Nodes mapped to universal type DNSRecord.",
    filters: { universal_type: "DNSRecord" },
  },
};

const SECTION_LABELS: Record<CatalogSection | "all", string> = {
  all: "All queries",
  security: "Security queries",
  blast_radius: "Blast radius queries",
};

function extractErrorMessage(body: Record<string, unknown>): string {
  if (typeof body?.message === "string" && body.message.trim()) {
    return body.message;
  }
  const output = body?.output;
  if (typeof output === "string" && output.trim()) {
    return output;
  }
  if (typeof output === "object" && output && !Array.isArray(output)) {
    const obj = output as Record<string, unknown>;
    if (typeof obj.message === "string" && obj.message.trim()) {
      return obj.message;
    }
    if (typeof obj.hint === "string" && obj.hint.trim()) {
      return `${obj.message || "Request failed"} — ${obj.hint}`;
    }
  }
  if (Array.isArray(output) && output.length > 0) {
    const first = output[0];
    if (typeof first === "object" && first && "message" in first) {
      return String((first as Record<string, unknown>).message);
    }
  }
  return "Request failed";
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

function statusBadgeVariant(status: RunStatus): "default" | "secondary" | "destructive" | "outline" {
  if (status === "success") return "default";
  if (status === "error") return "destructive";
  if (status === "running") return "secondary";
  return "outline";
}

function buildParamsRecord(
  paramNames: string[],
  values: Record<string, string>,
): Record<string, string | number> {
  const params: Record<string, string | number> = {};
  for (const name of paramNames) {
    const raw = values[name];
    if (raw === undefined || raw === "") continue;
    if (name === "min_dependents") {
      const parsed = Number(raw);
      params[name] = Number.isFinite(parsed) ? parsed : raw;
      continue;
    }
    params[name] = raw;
  }
  return params;
}

function paramValuesForItem(item: CatalogQuery): Record<string, string> {
  const nextParams: Record<string, string> = {};
  for (const param of item.params) {
    const defaultValue = item.default_params[param];
    nextParams[param] = defaultValue === undefined ? "" : String(defaultValue);
  }
  return nextParams;
}

function countOptions(map: Record<string, number> | undefined, fallback: string[]): SelectOption[] {
  if (map && Object.keys(map).length > 0) {
    return Object.entries(map)
      .sort((a, b) => b[1] - a[1])
      .map(([value, count]) => ({ value, label: `${value} (${count})`, count }));
  }
  return fallback.map((value) => ({ value, label: value }));
}

function providerOptions(
  map: Record<string, number> | undefined,
  fallback: Array<{ value: string; label: string }>,
): SelectOption[] {
  if (map && Object.keys(map).length > 0) {
    return Object.entries(map)
      .sort((a, b) => b[1] - a[1])
      .map(([value, count]) => ({ value, label: `${value} (${count})`, count }));
  }
  return fallback.map((item) => ({ value: item.value, label: item.label }));
}

export default function GroCypherCatalogProbe({ portfolio, org }: GroCypherCatalogProbeProps) {
  const [activeTab, setActiveTab] = useState<"queries" | "inspect">("inspect");

  const [edgeTypesRaw, setEdgeTypesRaw] = useState(DEFAULT_EDGE_TYPES.join("\n"));
  const [maxEdges, setMaxEdges] = useState("50000");
  const [reuseSnapshot, setReuseSnapshot] = useState(true);

  const [sectionFilter, setSectionFilter] = useState<CatalogSection | "all">("all");
  const [selectedId, setSelectedId] = useState<string>(QUERIES[0]?.id ?? "");
  const [queryText, setQueryText] = useState<string>(QUERIES[0]?.query ?? "");
  const [paramValues, setParamValues] = useState<Record<string, string>>(() =>
    QUERIES[0] ? paramValuesForItem(QUERIES[0]) : {},
  );
  const [runningSingle, setRunningSingle] = useState(false);
  const [runningAll, setRunningAll] = useState(false);
  const [queryRequest, setQueryRequest] = useState<Record<string, unknown> | null>(null);
  const [queryResponse, setQueryResponse] = useState<unknown>(null);
  const [queryError, setQueryError] = useState("");
  const [results, setResults] = useState<Record<string, QueryRunResult>>({});

  const [inspectUniversalType, setInspectUniversalType] = useState(ALL_VALUE);
  const [inspectProviderType, setInspectProviderType] = useState(ALL_VALUE);
  const [inspectRelationshipType, setInspectRelationshipType] = useState(ALL_VALUE);
  const [inspectNodeId, setInspectNodeId] = useState(ALL_VALUE);
  const [inspectNodeLimit, setInspectNodeLimit] = useState("25");
  const [inspectEdgeLimit, setInspectEdgeLimit] = useState("25");
  const [inspectPreset, setInspectPreset] = useState<InspectPresetId>("overview");
  const [inspecting, setInspecting] = useState(false);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [inspectRequest, setInspectRequest] = useState<Record<string, unknown> | null>(null);
  const [inspectResponse, setInspectResponse] = useState<unknown>(null);
  const [inspectError, setInspectError] = useState("");
  const [inspectSummary, setInspectSummary] = useState<InspectSummary | null>(null);
  const [knownNodeIds, setKnownNodeIds] = useState<string[]>([]);
  const [summaryLoaded, setSummaryLoaded] = useState(false);

  const filteredQueries = useMemo(() => {
    if (sectionFilter === "all") return QUERIES;
    return QUERIES.filter((item) => item.section === sectionFilter);
  }, [sectionFilter]);

  const selectedQuery = useMemo(
    () => QUERIES.find((item) => item.id === selectedId) ?? filteredQueries[0] ?? null,
    [selectedId, filteredQueries],
  );

  const endpoint = `${import.meta.env.VITE_API_URL}/_schd/${portfolio}/${org}/call/gro/cypher_query`;

  const buildSnapshotOptions = useCallback(() => {
    const edgeTypes = edgeTypesRaw
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
    return {
      edge_types: edgeTypes.length ? edgeTypes : DEFAULT_EDGE_TYPES,
      max_edges: Number(maxEdges) || 50000,
      reuse_snapshot: reuseSnapshot,
    };
  }, [edgeTypesRaw, maxEdges, reuseSnapshot]);

  const buildInspectPayload = useCallback(
    (overrides?: {
      universal_type?: string;
      provider_type?: string;
      relationship_type?: string;
      node_id_contains?: string;
      node_limit?: number;
      edge_limit?: number;
    }): Record<string, unknown> => {
      const universal =
        overrides?.universal_type ??
        (inspectUniversalType !== ALL_VALUE ? inspectUniversalType : undefined);
      const provider =
        overrides?.provider_type ??
        (inspectProviderType !== ALL_VALUE ? inspectProviderType : undefined);
      const relationship =
        overrides?.relationship_type ??
        (inspectRelationshipType !== ALL_VALUE ? inspectRelationshipType : undefined);
      const nodeContains =
        overrides?.node_id_contains ??
        (inspectNodeId !== ALL_VALUE ? inspectNodeId : undefined);

      return {
        portfolio,
        org,
        options: {
          ...buildSnapshotOptions(),
          inspect_only: true,
          inspect: {
            node_limit: overrides?.node_limit ?? (Number(inspectNodeLimit) || 25),
            edge_limit: overrides?.edge_limit ?? (Number(inspectEdgeLimit) || 25),
            ...(universal ? { universal_type: universal } : {}),
            ...(provider ? { provider_type: provider } : {}),
            ...(relationship ? { relationship_type: relationship } : {}),
            ...(nodeContains ? { node_id_contains: nodeContains } : {}),
          },
        },
      };
    },
    [
      portfolio,
      org,
      buildSnapshotOptions,
      inspectUniversalType,
      inspectProviderType,
      inspectRelationshipType,
      inspectNodeId,
      inspectNodeLimit,
      inspectEdgeLimit,
    ],
  );

  const callCypherHandler = useCallback(
    async (payload: Record<string, unknown>) => {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${sessionStorage.accessToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });
      const body = await response.json();
      const output = unwrapHandlerOutput(body);
      const ok = response.ok && Boolean(body?.success) && output?.success !== false;
      return {
        ok,
        body,
        output,
        error: ok ? "" : extractErrorMessage(body) || String(output?.message || "Request failed"),
      };
    },
    [endpoint],
  );

  const applyPreset = useCallback((presetId: InspectPresetId) => {
    const preset = INSPECT_PRESETS[presetId];
    setInspectPreset(presetId);
    setInspectUniversalType(preset.filters.universal_type ?? ALL_VALUE);
    setInspectProviderType(preset.filters.provider_type ?? ALL_VALUE);
    setInspectRelationshipType(preset.filters.relationship_type ?? ALL_VALUE);
    setInspectNodeId(ALL_VALUE);
  }, []);

  const runInspect = useCallback(
    async (payload?: Record<string, unknown>) => {
      setInspecting(true);
      setInspectError("");
      const request = payload ?? buildInspectPayload();
      setInspectRequest(request);
      try {
        const { ok, body, output, error } = await callCypherHandler(request);
        if (!ok) {
          setInspectError(error);
          setInspectResponse(body?.output ?? body);
          return;
        }
        setInspectResponse(output);

        const result = output?.result as Record<string, unknown> | undefined;
        const summary = result?.summary as InspectSummary | undefined;
        if (summary) {
          setInspectSummary(summary);
          setSummaryLoaded(true);
        }
        const sampleNodes = result?.sample_nodes;
        if (Array.isArray(sampleNodes)) {
          const ids = sampleNodes
            .map((node) => (typeof node === "object" && node ? String((node as Record<string, unknown>).node_id || "") : ""))
            .filter(Boolean);
          if (ids.length > 0) {
            setKnownNodeIds((prev) => Array.from(new Set([...prev, ...ids])).slice(0, 200));
          }
        }
      } catch (err: any) {
        setInspectError(err?.message || "Unexpected error inspecting snapshot");
      } finally {
        setInspecting(false);
      }
    },
    [buildInspectPayload, callCypherHandler],
  );

  const loadSnapshotSummary = useCallback(async () => {
    setLoadingSummary(true);
    setInspectError("");
    const request = buildInspectPayload({
      node_limit: 50,
      edge_limit: 50,
    });
    setInspectRequest(request);
    try {
      const { ok, body, output, error } = await callCypherHandler(request);
      if (!ok) {
        setInspectError(error);
        setInspectResponse(body?.output ?? body);
        return;
      }
      setInspectResponse(output);
      const result = output?.result as Record<string, unknown> | undefined;
      const summary = result?.summary as InspectSummary | undefined;
      if (summary) {
        setInspectSummary(summary);
        setSummaryLoaded(true);
      }
      const sampleNodes = result?.sample_nodes;
      if (Array.isArray(sampleNodes)) {
        const ids = sampleNodes
          .map((node) => (typeof node === "object" && node ? String((node as Record<string, unknown>).node_id || "") : ""))
          .filter(Boolean);
        setKnownNodeIds(ids.slice(0, 200));
      }
    } catch (err: any) {
      setInspectError(err?.message || "Unexpected error loading snapshot summary");
    } finally {
      setLoadingSummary(false);
    }
  }, [buildInspectPayload, callCypherHandler]);

  useEffect(() => {
    if (activeTab !== "inspect" || summaryLoaded) return;
    void loadSnapshotSummary();
  }, [activeTab, summaryLoaded, loadSnapshotSummary]);

  const universalTypeOptions = useMemo(
    () => countOptions(inspectSummary?.nodes_by_universal_type, FALLBACK_UNIVERSAL_TYPES),
    [inspectSummary],
  );

  const providerTypeOptions = useMemo(
    () => providerOptions(inspectSummary?.provider_types_seen, FALLBACK_PROVIDER_TYPES),
    [inspectSummary],
  );

  const relationshipOptions = useMemo(
    () => countOptions(inspectSummary?.edges_by_relationship_type, FALLBACK_RELATIONSHIPS),
    [inspectSummary],
  );

  const buildRequestPayload = (
    item: CatalogQuery,
    queryOverride?: string,
    paramOverride?: Record<string, string>,
  ): Record<string, unknown> => {
    const effectiveParams = paramOverride ?? paramValues;
    const params = buildParamsRecord(item.params, effectiveParams);
    return {
      portfolio,
      org,
      query_text: queryOverride ?? queryText,
      params,
      options: buildSnapshotOptions(),
    };
  };

  const executeQuery = async (
    item: CatalogQuery,
    queryOverride?: string,
    paramOverride?: Record<string, string>,
  ): Promise<QueryRunResult> => {
    const started = performance.now();
    const request = buildRequestPayload(item, queryOverride, paramOverride);
    try {
      const { ok, body, output, error } = await callCypherHandler(request);
      const durationMs = Math.round(performance.now() - started);
      if (!ok) {
        return {
          status: "error",
          request,
          response: body?.output ?? body,
          error,
          durationMs,
          rowCount: null,
          finishedAt: new Date().toISOString(),
        };
      }
      const result = output?.result;
      const rowCount =
        typeof result === "object" && result && "row_count" in result
          ? Number((result as Record<string, unknown>).row_count)
          : null;
      return {
        status: "success",
        request,
        response: output,
        error: "",
        durationMs,
        rowCount: Number.isFinite(rowCount) ? rowCount : null,
        finishedAt: new Date().toISOString(),
      };
    } catch (err: any) {
      return {
        status: "error",
        request,
        response: null,
        error: err?.message || "Unexpected error executing query",
        durationMs: Math.round(performance.now() - started),
        rowCount: null,
        finishedAt: new Date().toISOString(),
      };
    }
  };

  const selectQuery = (item: CatalogQuery) => {
    setSelectedId(item.id);
    setQueryText(item.query);
    setParamValues(paramValuesForItem(item));
  };

  const runSelected = async () => {
    if (!selectedQuery) return;
    setRunningSingle(true);
    setQueryError("");
    setResults((prev) => ({
      ...prev,
      [selectedQuery.id]: {
        status: "running",
        request: buildRequestPayload(selectedQuery),
        response: null,
        error: "",
        durationMs: 0,
        rowCount: null,
        finishedAt: "",
      },
    }));
    const result = await executeQuery(selectedQuery, queryText);
    setQueryRequest(result.request);
    setQueryResponse(result.response);
    setQueryError(result.error);
    setResults((prev) => ({ ...prev, [selectedQuery.id]: result }));
    setRunningSingle(false);
  };

  const runAll = async () => {
    setRunningAll(true);
    setQueryError("");
    for (const item of filteredQueries) {
      const itemParams = paramValuesForItem(item);
      setResults((prev) => ({
        ...prev,
        [item.id]: {
          status: "running",
          request: buildRequestPayload(item, item.query, itemParams),
          response: null,
          error: "",
          durationMs: 0,
          rowCount: null,
          finishedAt: "",
        },
      }));
      selectQuery(item);
      setQueryText(item.query);
      const result = await executeQuery(item, item.query, itemParams);
      setResults((prev) => ({ ...prev, [item.id]: result }));
      setQueryRequest(result.request);
      setQueryResponse(result.response);
      setQueryError(result.error);
    }
    setRunningAll(false);
  };

  const resetQueryResults = () => {
    setResults({});
    setQueryRequest(null);
    setQueryResponse(null);
    setQueryError("");
  };

  const successCount = filteredQueries.filter((item) => results[item.id]?.status === "success").length;
  const errorCount = filteredQueries.filter((item) => results[item.id]?.status === "error").length;
  const testedCount = filteredQueries.filter(
    (item) => results[item.id]?.status === "success" || results[item.id]?.status === "error",
  ).length;

  const snapshotSettings = (
    <div className="grid gap-3 rounded border p-3 md:grid-cols-3">
      <div className="grid gap-2">
        <label className="text-xs font-medium">Max edges (snapshot load)</label>
        <Input value={maxEdges} onChange={(e) => setMaxEdges(e.target.value)} />
      </div>
      <div className="grid gap-2">
        <label className="text-xs font-medium">Reuse snapshot in memory</label>
        <Select value={reuseSnapshot ? "true" : "false"} onValueChange={(value) => setReuseSnapshot(value === "true")}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="true">Yes — faster repeat inspects/queries</SelectItem>
            <SelectItem value="false">No — reload from graph DB each time</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="md:col-span-3 grid gap-2">
        <label className="text-xs font-medium">Edge types to scan (one per line)</label>
        <Textarea
          className="min-h-[72px] font-mono text-xs"
          value={edgeTypesRaw}
          onChange={(e) => {
            setEdgeTypesRaw(e.target.value);
            setSummaryLoaded(false);
          }}
        />
      </div>
    </div>
  );

  return (
    <Card className="mx-auto w-full overflow-hidden sm:w-11/12">
      <CardHeader>
        <CardTitle>Cybersecurity Cypher Catalog Probe</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4">
        <div className="text-xs text-muted-foreground">
          Use <strong>Cache inspection</strong> to verify ontology mapping on the in-memory snapshot. Use{" "}
          <strong>Query catalog</strong> to run cybersecurity Cypher queries. Inspect does not require running a
          query first — it loads the snapshot itself.
        </div>

        {snapshotSettings}

        <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as "queries" | "inspect")}>
          <TabsList>
            <TabsTrigger value="inspect">Cache inspection</TabsTrigger>
            <TabsTrigger value="queries">Query catalog</TabsTrigger>
          </TabsList>

          <TabsContent value="inspect" className="grid gap-4 pt-4">
            <div className="grid gap-3 rounded border p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="text-sm font-medium">Snapshot filters</div>
                {inspectSummary && (
                  <Badge variant="outline">
                    {inspectSummary.total_nodes} nodes · {inspectSummary.total_edges} edges loaded
                  </Badge>
                )}
              </div>

              <div className="grid gap-2">
                <label className="text-xs font-medium">Quick preset</label>
                <Select
                  value={inspectPreset}
                  onValueChange={(value) => applyPreset(value as InspectPresetId)}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {(Object.keys(INSPECT_PRESETS) as InspectPresetId[]).map((presetId) => (
                      <SelectItem key={presetId} value={presetId}>
                        {INSPECT_PRESETS[presetId].label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <div className="text-xs text-muted-foreground">{INSPECT_PRESETS[inspectPreset].description}</div>
              </div>

              <div className="grid gap-2 md:grid-cols-2">
                <FilterSelect
                  label="Universal type"
                  value={inspectUniversalType}
                  onChange={setInspectUniversalType}
                  options={universalTypeOptions}
                />
                <FilterSelect
                  label="Provider type"
                  value={inspectProviderType}
                  onChange={setInspectProviderType}
                  options={providerTypeOptions}
                />
                <FilterSelect
                  label="Relationship type"
                  value={inspectRelationshipType}
                  onChange={setInspectRelationshipType}
                  options={relationshipOptions}
                />
                <FilterSelect
                  label="Node id (from samples)"
                  value={inspectNodeId}
                  onChange={setInspectNodeId}
                  options={knownNodeIds.map((id) => ({ value: id, label: id }))}
                  emptyLabel="Load snapshot first to pick node ids"
                />
                <div className="grid gap-1">
                  <label className="text-xs text-muted-foreground">Node sample limit</label>
                  <Select value={inspectNodeLimit} onValueChange={setInspectNodeLimit}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {["10", "25", "50", "100"].map((value) => (
                        <SelectItem key={value} value={value}>
                          {value}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="grid gap-1">
                  <label className="text-xs text-muted-foreground">Edge sample limit</label>
                  <Select value={inspectEdgeLimit} onValueChange={setInspectEdgeLimit}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {["10", "25", "50", "100"].map((value) => (
                        <SelectItem key={value} value={value}>
                          {value}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              {inspectSummary && inspectSummary.unmapped_provider_types.length > 0 && (
                <div className="rounded bg-amber-50 p-2 text-xs text-amber-900">
                  Unmapped provider types (labeled as Resource):{" "}
                  {inspectSummary.unmapped_provider_types.slice(0, 10).join(", ")}
                  {inspectSummary.unmapped_provider_types.length > 10 ? " …" : ""}
                </div>
              )}
            </div>

            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                onClick={() => void loadSnapshotSummary()}
                disabled={loadingSummary || inspecting}
              >
                {loadingSummary ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Database className="mr-2 h-4 w-4" />
                )}
                Reload snapshot summary
              </Button>
              <Button onClick={() => void runInspect()} disabled={inspecting || loadingSummary}>
                {inspecting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Search className="mr-2 h-4 w-4" />}
                Inspect with filters
              </Button>
              <Button
                variant="secondary"
                onClick={() => {
                  applyPreset("overview");
                  void runInspect({
                    portfolio,
                    org,
                    options: {
                      ...buildSnapshotOptions(),
                      inspect_only: true,
                      inspect: {
                        node_limit: 25,
                        edge_limit: 25,
                      },
                    },
                  });
                }}
                disabled={inspecting || loadingSummary}
              >
                Run recommended default
              </Button>
            </div>

            {inspectError && <div className="text-sm text-red-600">{inspectError}</div>}

            <IoPanel
              request={inspectRequest}
              response={inspectResponse}
              emptyMessage="Opening this tab loads the snapshot automatically. Use the buttons above to inspect filtered samples."
            />
          </TabsContent>

          <TabsContent value="queries" className="grid gap-4 pt-4">
            <div className="grid gap-3 rounded border p-3 md:grid-cols-3">
              <div className="grid gap-2">
                <label className="text-xs font-medium">Catalog section</label>
                <Select
                  value={sectionFilter}
                  onValueChange={(value) => setSectionFilter(value as CatalogSection | "all")}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">{SECTION_LABELS.all}</SelectItem>
                    <SelectItem value="security">{SECTION_LABELS.security}</SelectItem>
                    <SelectItem value="blast_radius">{SECTION_LABELS.blast_radius}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <Button onClick={runSelected} disabled={runningSingle || runningAll || !selectedQuery}>
                {runningSingle ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <PlayCircle className="mr-2 h-4 w-4" />
                )}
                Run selected
              </Button>
              <Button
                variant="secondary"
                onClick={runAll}
                disabled={runningSingle || runningAll || filteredQueries.length === 0}
              >
                {runningAll ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <ListChecks className="mr-2 h-4 w-4" />}
                Run all in section ({filteredQueries.length})
              </Button>
              <Button variant="outline" onClick={resetQueryResults} disabled={runningSingle || runningAll}>
                <RotateCcw className="mr-2 h-4 w-4" />
                Reset results
              </Button>
              <Badge variant="outline">
                Tested {testedCount}/{filteredQueries.length}
              </Badge>
              <Badge variant="default">Success {successCount}</Badge>
              <Badge variant="destructive">Errors {errorCount}</Badge>
            </div>

            <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
              <div className="grid max-h-[720px] gap-2 overflow-auto rounded border p-2">
                {filteredQueries.map((item) => {
                  const result = results[item.id];
                  const status: RunStatus = result?.status ?? "idle";
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => selectQuery(item)}
                      className={
                        selectedId === item.id
                          ? "rounded border bg-muted p-2 text-left"
                          : "rounded border border-transparent p-2 text-left hover:bg-muted/60"
                      }
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="text-xs font-medium">
                          {item.section === "security" ? "S" : "B"}
                          {item.number}. {item.title}
                        </div>
                        <Badge variant={statusBadgeVariant(status)} className="shrink-0 text-[10px]">
                          {status}
                        </Badge>
                      </div>
                      {result?.rowCount !== null && result?.rowCount !== undefined && (
                        <div className="mt-1 text-[10px] text-muted-foreground">
                          {result.rowCount} rows · {result.durationMs}ms
                        </div>
                      )}
                      {result?.error && (
                        <div className="mt-1 line-clamp-2 text-[10px] text-red-600">{result.error}</div>
                      )}
                    </button>
                  );
                })}
              </div>

              <div className="grid gap-4">
                {selectedQuery && (
                  <>
                    <div className="grid gap-2">
                      <div className="text-sm font-medium">{selectedQuery.title}</div>
                      {selectedQuery.description && (
                        <div className="text-xs text-muted-foreground">{selectedQuery.description}</div>
                      )}
                    </div>

                    {selectedQuery.params.length > 0 && (
                      <div className="grid gap-2 rounded border p-3 md:grid-cols-2">
                        {selectedQuery.params.map((param) => (
                          <div key={param} className="grid gap-1">
                            <label className="text-xs font-medium">${param}</label>
                            <Input
                              value={paramValues[param] ?? ""}
                              onChange={(e) =>
                                setParamValues((prev) => ({
                                  ...prev,
                                  [param]: e.target.value,
                                }))
                              }
                              placeholder={`Value for $${param}`}
                            />
                          </div>
                        ))}
                      </div>
                    )}

                    <div className="grid gap-2">
                      <label className="text-xs font-medium">Cypher query (editable)</label>
                      <Textarea
                        className="min-h-[220px] font-mono text-xs"
                        value={queryText}
                        onChange={(e) => setQueryText(e.target.value)}
                      />
                    </div>
                  </>
                )}

                {queryError && <div className="text-sm text-red-600">{queryError}</div>}

                <IoPanel
                  request={queryRequest ?? (selectedQuery ? buildRequestPayload(selectedQuery) : null)}
                  response={queryResponse}
                  emptyMessage="Select a catalog query and run it to see input/output."
                />
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
  emptyLabel = "No options yet",
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  emptyLabel?: string;
}) {
  return (
    <div className="grid gap-1">
      <label className="text-xs text-muted-foreground">{label}</label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger>
          <SelectValue placeholder={emptyLabel} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL_VALUE}>All (no filter)</SelectItem>
          {options.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

function IoPanel({
  request,
  response,
  emptyMessage,
}: {
  request: Record<string, unknown> | null;
  response: unknown;
  emptyMessage: string;
}) {
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Request input</CardTitle>
        </CardHeader>
        <CardContent>
          <pre className="max-h-[420px] overflow-auto rounded bg-muted p-3 text-xs">
            {request ? JSON.stringify(request, null, 2) : emptyMessage}
          </pre>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Handler output</CardTitle>
        </CardHeader>
        <CardContent>
          <pre className="max-h-[420px] overflow-auto rounded bg-muted p-3 text-xs">
            {response ? JSON.stringify(response, null, 2) : emptyMessage}
          </pre>
        </CardContent>
      </Card>
    </div>
  );
}
