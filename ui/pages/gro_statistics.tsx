import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Loader2, RefreshCw } from "lucide-react";

interface GroStatisticsProps {
  portfolio: string;
  org: string;
}

type Totals = {
  node_types: number;
  total_nodes: number;
  property_entries: number;
  edge_types: number;
  total_edges: number;
};

type EdgeFanoutMetrics = {
  from_node?: string;
  to_node?: string;
  edge_type?: string;
  total_edges?: number;
  distinct_sources?: number;
  avg_fanout?: number;
  max_fanout?: number;
};

type PersistedStats = {
  node_counts?: Record<string, number | string>;
  property_cardinality?: Record<string, number | string>;
  edge_fanout?: Record<string, EdgeFanoutMetrics>;
};

type StatsPayload = {
  totals?: Totals;
  stats?: PersistedStats;
  message?: string;
};

type NodeTypeRow = {
  nodeType: string;
  nodeCount: number;
  propertyEntries: number;
  edgeTypes: number;
  totalEdges: number;
};

const SAMPLE_NODES = ["knowledge_concepts", "knowledge_claims", "knowledge_reviews"].join("\n");

function extractHandlerOutput(body: Record<string, unknown>): Record<string, unknown> {
  const output = body?.output;
  if (Array.isArray(output) && output.length > 0 && typeof output[0] === "object" && output[0]) {
    return output[0] as Record<string, unknown>;
  }
  if (typeof output === "object" && output && !Array.isArray(output)) {
    return output as Record<string, unknown>;
  }
  return body;
}

function extractErrorMessage(body: Record<string, unknown>): string {
  const output = body?.output;
  if (Array.isArray(output) && output.length > 0) {
    const first = output[0];
    if (typeof first === "object" && first && "message" in first) {
      return String(first.message);
    }
    return output.map((item) => (typeof item === "string" ? item : JSON.stringify(item))).join("; ");
  }
  if (typeof output === "object" && output && !Array.isArray(output) && "message" in output) {
    return String(output.message);
  }
  if (typeof output === "string") {
    return output;
  }
  return String(body?.message || "Request failed");
}

function parseNodes(raw: string): string[] {
  return raw
    .split(/[\n,]+/)
    .map((node) => node.trim().toLowerCase().replace(/\s+/g, "_"))
    .filter(Boolean);
}

function toInt(value: unknown): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function parseEdgeFanoutFromNode(key: string, metrics: EdgeFanoutMetrics): string {
  const fromNode = String(metrics.from_node ?? "").trim();
  if (fromNode) {
    return fromNode;
  }
  const arrowIndex = key.indexOf("->");
  if (arrowIndex > 0) {
    return key.slice(0, arrowIndex).trim();
  }
  return "";
}

function buildNodeTypeRows(stats: PersistedStats | undefined): NodeTypeRow[] {
  if (!stats) {
    return [];
  }

  const nodeCounts = stats.node_counts ?? {};
  const propertyCardinality = stats.property_cardinality ?? {};
  const edgeFanout = stats.edge_fanout ?? {};

  const propertyEntriesByNode = new Map<string, number>();
  for (const key of Object.keys(propertyCardinality)) {
    const nodeType = key.split(".", 1)[0]?.trim();
    if (!nodeType) {
      continue;
    }
    propertyEntriesByNode.set(nodeType, (propertyEntriesByNode.get(nodeType) ?? 0) + 1);
  }

  const edgeTypesByNode = new Map<string, Set<string>>();
  const totalEdgesByNode = new Map<string, number>();
  for (const [key, rawMetrics] of Object.entries(edgeFanout)) {
    if (!rawMetrics || typeof rawMetrics !== "object") {
      continue;
    }
    const metrics = rawMetrics as EdgeFanoutMetrics;
    const fromNode = parseEdgeFanoutFromNode(key, metrics);
    if (!fromNode) {
      continue;
    }
    const edgeLabel = String(metrics.edge_type ?? key).trim();
    if (!edgeTypesByNode.has(fromNode)) {
      edgeTypesByNode.set(fromNode, new Set());
    }
    edgeTypesByNode.get(fromNode)?.add(edgeLabel);
    totalEdgesByNode.set(fromNode, (totalEdgesByNode.get(fromNode) ?? 0) + toInt(metrics.total_edges));
  }

  const nodeTypes = new Set<string>([
    ...Object.keys(nodeCounts),
    ...propertyEntriesByNode.keys(),
    ...edgeTypesByNode.keys(),
  ]);

  return [...nodeTypes]
    .sort((left, right) => left.localeCompare(right))
    .map((nodeType) => ({
      nodeType,
      nodeCount: toInt(nodeCounts[nodeType]),
      propertyEntries: propertyEntriesByNode.get(nodeType) ?? 0,
      edgeTypes: edgeTypesByNode.get(nodeType)?.size ?? 0,
      totalEdges: totalEdgesByNode.get(nodeType) ?? 0,
    }));
}

export default function GroStatistics({ portfolio, org }: GroStatisticsProps) {
  const [loading, setLoading] = useState(true);
  const [recalculating, setRecalculating] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [summary, setSummary] = useState<StatsPayload | null>(null);
  const [nodesRaw, setNodesRaw] = useState(SAMPLE_NODES);

  const endpoint = (handler: string) =>
    `${import.meta.env.VITE_API_URL}/_schd/${portfolio}/${org}/call/gro/${handler}`;

  const callHandler = async (handler: string, payload: Record<string, unknown>) => {
    const response = await fetch(endpoint(handler), {
      method: "POST",
      headers: {
        Authorization: `Bearer ${sessionStorage.accessToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
    const body = await response.json();
    if (!response.ok || !body?.success) {
      throw new Error(extractErrorMessage(body));
    }
    return extractHandlerOutput(body);
  };

  const loadSummary = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const output = await callHandler("graph_statistics_summary", { portfolio, org });
      setSummary(output as StatsPayload);
    } catch (err: any) {
      setSummary(null);
      setError(err?.message || "Failed to load statistics");
    } finally {
      setLoading(false);
    }
  }, [portfolio, org]);

  useEffect(() => {
    loadSummary();
  }, [loadSummary]);

  const recalculate = async () => {
    setRecalculating(true);
    setError("");
    setNotice("");

    const nodes = parseNodes(nodesRaw);
    if (nodes.length === 0) {
      setError("Enter at least one node type to synchronize");
      setRecalculating(false);
      return;
    }

    try {
      const output = await callHandler("graph_statistics_registry", {
        portfolio,
        org,
        sync_scope: {
          nodes,
        },
      });
      const parts: string[] = [];
      if (output.message) {
        parts.push(String(output.message));
      }
      if (Array.isArray(output.inferred_relationships) && output.inferred_relationships.length > 0) {
        parts.push(
          `inferred ${output.inferred_relationships.length} relationship(s) from blueprints`,
        );
      }
      if (output.skipped && typeof output.skipped === "object") {
        const skipped = output.skipped as { rings?: string[]; edges?: string[] };
        if (skipped.rings?.length) {
          parts.push(`skipped rings without blueprint: ${skipped.rings.join(", ")}`);
        }
        if (skipped.edges?.length) {
          parts.push(`skipped edges without source blueprint: ${skipped.edges.join(", ")}`);
        }
      }
      if (parts.length) {
        setNotice(parts.join("; "));
      }
      await loadSummary();
    } catch (err: any) {
      setError(err?.message || "Failed to recalculate statistics");
    } finally {
      setRecalculating(false);
    }
  };

  const totals = summary?.totals;
  const nodeTypeRows = useMemo(() => buildNodeTypeRows(summary?.stats), [summary?.stats]);

  return (
    <Card className="mx-auto w-full sm:w-11/12 overflow-hidden">
      <CardHeader>
        <CardTitle>Graph Statistics</CardTitle>
        <p className="text-xs text-muted-foreground mt-1">
          Persisted totals used by the cost estimator. Recalculate periodically, not on every query.
        </p>
      </CardHeader>
      <CardContent className="grid gap-4">
        {loading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading persisted statistics...
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-3">
            <Card>
              <CardContent className="pt-4">
                <div className="text-xs text-muted-foreground">Nodes</div>
                <div className="text-2xl font-semibold">{totals?.total_nodes ?? 0}</div>
                <div className="text-xs text-muted-foreground">{totals?.node_types ?? 0} node types</div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4">
                <div className="text-xs text-muted-foreground">Properties</div>
                <div className="text-2xl font-semibold">{totals?.property_entries ?? 0}</div>
                <div className="text-xs text-muted-foreground">cardinality entries</div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-4">
                <div className="text-xs text-muted-foreground">Fanout</div>
                <div className="text-2xl font-semibold">{totals?.total_edges ?? 0}</div>
                <div className="text-xs text-muted-foreground">{totals?.edge_types ?? 0} edge types</div>
              </CardContent>
            </Card>
          </div>
        )}

        {!loading && nodeTypeRows.length > 0 && (
          <div className="grid gap-2">
            <div className="text-sm font-medium">By node type</div>
            <p className="text-xs text-muted-foreground">
              Breakdown from the persisted summary already loaded above (no extra database call).
            </p>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Node type</TableHead>
                  <TableHead className="text-right">Nodes</TableHead>
                  <TableHead className="text-right">Properties</TableHead>
                  <TableHead className="text-right">Edge types</TableHead>
                  <TableHead className="text-right">Fanout edges</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {nodeTypeRows.map((row) => (
                  <TableRow key={row.nodeType}>
                    <TableCell className="font-mono text-xs">{row.nodeType}</TableCell>
                    <TableCell className="text-right tabular-nums">{row.nodeCount}</TableCell>
                    <TableCell className="text-right tabular-nums">{row.propertyEntries}</TableCell>
                    <TableCell className="text-right tabular-nums">{row.edgeTypes}</TableCell>
                    <TableCell className="text-right tabular-nums">{row.totalEdges}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}

        <div className="grid gap-3">
          <div className="text-sm font-medium">Sync scope</div>
          <p className="text-xs text-muted-foreground">
            Declare blueprint ring names to aggregate. Relationships and countable fields are
            inferred from each ring&apos;s blueprint (source fields and countable flags).
          </p>
          <div className="grid gap-2">
            <div className="text-xs font-medium">Node types (one per line or comma-separated)</div>
            <Textarea
              className="min-h-[100px] font-mono text-xs"
              value={nodesRaw}
              onChange={(e) => setNodesRaw(e.target.value)}
            />
          </div>
          <Button onClick={recalculate} disabled={loading || recalculating}>
            {recalculating ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
            Recalculate
          </Button>
        </div>

        {notice && <div className="text-sm text-amber-700">{notice}</div>}
        {error && <div className="text-sm text-red-600">{error}</div>}

        {summary?.stats && (
          <details className="rounded border bg-muted/40 p-3 text-xs">
            <summary className="cursor-pointer font-medium">Raw persisted stats</summary>
            <pre className="mt-2 overflow-auto max-h-[420px]">
              {JSON.stringify(summary.stats, null, 2)}
            </pre>
          </details>
        )}
      </CardContent>
    </Card>
  );
}
