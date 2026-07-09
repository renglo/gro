import { EllipsisVertical, GitBranch } from "lucide-react";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { useState } from "react";

interface ToolMenuProps {
  portfolio: string;
  org: string;
  tool?: string;
  section?: string;
  onNavigate: (path: string) => void;
}

export default function ToolGroSheetNav({ portfolio, org, tool, onNavigate }: ToolMenuProps) {
  const [open, setOpen] = useState(false);

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button size="icon" variant="outline" className="block sm:hidden">
          <EllipsisVertical className="h-5 w-5" />
          <span className="sr-only">Toggle Menu</span>
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="sm:max-w-xs">
        <nav className="grid gap-4 text-lg font-medium">
          <button
            onClick={() => {
              setOpen(false);
              onNavigate(`/${portfolio}/${org}/${tool}/pipeline`);
            }}
            className="flex items-center gap-4 px-2.5 text-foreground"
          >
            <GitBranch className="h-5 w-5" />
            Gro Pipeline
          </button>
          <button
            onClick={() => {
              setOpen(false);
              onNavigate(`/${portfolio}/${org}/${tool}/executor`);
            }}
            className="flex items-center gap-4 px-2.5 text-foreground"
          >
            <GitBranch className="h-5 w-5" />
            Gro Executor
          </button>
          <button
            onClick={() => {
              setOpen(false);
              onNavigate(`/${portfolio}/${org}/${tool}/nl_query`);
            }}
            className="flex items-center gap-4 px-2.5 text-foreground"
          >
            <GitBranch className="h-5 w-5" />
            NL Query
          </button>
          <button
            onClick={() => {
              setOpen(false);
              onNavigate(`/${portfolio}/${org}/${tool}/cypher_catalog`);
            }}
            className="flex items-center gap-4 px-2.5 text-foreground"
          >
            <GitBranch className="h-5 w-5" />
            Cypher Catalog
          </button>
          <button
            onClick={() => {
              setOpen(false);
              onNavigate(`/${portfolio}/${org}/${tool}/statistics`);
            }}
            className="flex items-center gap-4 px-2.5 text-foreground"
          >
            <GitBranch className="h-5 w-5" />
            Graph Statistics
          </button>
        </nav>
      </SheetContent>
    </Sheet>
  );
}
