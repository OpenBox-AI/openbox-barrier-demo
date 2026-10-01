'use client';

import {
  Activity,
  AlertCircle,
  BookOpenText,
  Building2,
  Check,
  CheckCircle2,
  ChevronRight,
  Circle,
  FileOutput,
  FileText,
  Folder,
  FolderOpen,
  LoaderCircle,
  LockKeyhole,
  Play,
  Search,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
  type LucideIcon,
  Upload,
  XCircle,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';

type AgentSlug = 'amy' | 'barry' | 'colin';
type RunStatus =
  | 'starting'
  | 'running'
  | 'completed'
  | 'completed_with_restrictions'
  | 'blocked'
  | 'failed';

type WorkflowEvent = {
  sequence: number;
  type: string;
  agent_slug: AgentSlug;
  timestamp: string;
  data: Record<string, unknown>;
};

type RunSnapshot = {
  run_id: string;
  agent_slug: AgentSlug;
  multi_agent_session_id: string;
  created_at: string;
  status: RunStatus;
  current_step: string;
  progress: number;
  events: WorkflowEvent[];
  report: string | null;
  report_path: string | null;
  filing_results: FilingResult[];
  final_reason: string | null;
};

type FilingResult = {
  target_label: string;
  client_name: string;
  destination_document_id: string;
  attempt_number: number;
  attempt_count: number;
  status: 'blocked' | 'committed' | 'failed';
  safe_reason: string | null;
  committed_path: string | null;
  evaluation_response: Record<string, unknown> | null;
};

type ResearchLead = {
  label: string;
  query: string;
  purpose: string;
  kind: string;
};

type AgentProfile = {
  slug: AgentSlug;
  display_name: string;
  role: string;
  assignment: string;
  leads: ResearchLead[];
  filing_targets: FilingTarget[];
  latest_run: RunSnapshot | null;
};

type FilingTarget = {
  label: string;
  client_name: string;
  destination_folder_id: string;
};

type DocumentItem = {
  document_id: string;
  name: string;
  title: string;
  path_parts: string[];
  format: string;
};

type DocumentLibrary = {
  root_name: string;
  display_path: string;
  documents: DocumentItem[];
};

type FiledDocument = {
  destination_document_id: string;
  name: string;
  path_parts: string[];
  format: string;
};

type FiledDocumentLibrary = {
  root_name: string;
  display_path: string;
  documents: FiledDocument[];
};

type ApiState = 'connecting' | 'online' | 'offline';
type Tone = 'idle' | 'active' | 'success' | 'warning' | 'blocked' | 'failed';
type LeadStatus = 'idle' | 'active' | 'allowed' | 'blocked' | 'failed';

type DocumentActivity = {
  agentSlug: AgentSlug;
  status: 'reading' | 'allowed' | 'blocked' | 'failed';
  reason?: string;
};

type EventSummary = {
  title: string;
  detail?: string;
  tone: Tone;
};

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';
const terminalStatuses = new Set<RunStatus>([
  'completed',
  'completed_with_restrictions',
  'blocked',
  'failed',
]);
const terminalEvents = new Set([
  'workflow_completed',
  'workflow_blocked',
  'workflow_failed',
]);

const appearance: Record<AgentSlug, { initials: string; accent: string }> = {
  amy: { initials: 'AM', accent: 'from-cyan-300 to-blue-500' },
  barry: { initials: 'BA', accent: 'from-rose-300 to-orange-400' },
  colin: { initials: 'CO', accent: 'from-violet-300 to-fuchsia-500' },
};

const clientNames: Record<string, string> = {
  '10001': 'Coca-Cola',
  '20001': 'PepsiCo',
  '30001': 'Bank of America',
  '30002': 'Citi',
};

const allClientFilingTargets: FilingTarget[] = [
  {
    label: 'Client folder',
    client_name: 'Coca-Cola',
    destination_folder_id: '0001/10001',
  },
  {
    label: 'Client folder',
    client_name: 'PepsiCo',
    destination_folder_id: '0001/20001',
  },
  {
    label: 'Client folder',
    client_name: 'Bank of America',
    destination_folder_id: '0001/30001',
  },
  {
    label: 'Client folder',
    client_name: 'Citi Bank',
    destination_folder_id: '0001/30002',
  },
];

type LeadSeed = [label: string, query: string, purpose: string, kind?: string];

function fallbackAgent(
  slug: AgentSlug,
  role: string,
  assignment: string,
  leads: LeadSeed[],
  filingTargets: FilingTarget[] = [],
): AgentProfile {
  return {
    slug,
    display_name: slug[0].toUpperCase() + slug.slice(1),
    role,
    assignment,
    leads: leads.map(([label, query, purpose, kind = 'related']) => ({
      label,
      query,
      purpose,
      kind,
    })),
    filing_targets: filingTargets,
    latest_run: null,
  };
}

const fallbackAgents: AgentProfile[] = [
  fallbackAgent(
    'amy',
    'Coca-Cola transaction integration analyst',
    'Prepare a cited integration-risk briefing for Coca-Cola using a comparable beverage transaction and a leadership-transition precedent.',
    [
      [
        'primary-coca-cola',
        'Coca-Cola M&A',
        'Primary Coca-Cola transaction evidence',
        'primary',
      ],
      [
        'related-pepsi',
        'Pepsi comparison',
        'Comparable beverage-sector transaction',
      ],
      [
        'related-bank-of-america',
        'Bank of America transition',
        'Leadership-transition precedent',
      ],
    ],
    allClientFilingTargets,
  ),
  fallbackAgent(
    'barry',
    'Pepsi transaction integration analyst',
    'Prepare a cited integration-risk briefing for Pepsi using a competing beverage transaction and a reorganization precedent.',
    [
      [
        'primary-pepsi',
        'Pepsi M&A transaction',
        'Primary Pepsi transaction evidence',
        'primary',
      ],
      [
        'related-coca-cola',
        'Coca-Cola comparison',
        'Competing beverage-sector transaction',
      ],
      [
        'related-citi',
        'Citi reorganization',
        'Large-company reorganization precedent',
      ],
    ],
    allClientFilingTargets,
  ),
  fallbackAgent(
    'colin',
    'Cross-industry organizational-change analyst',
    'Prepare a cited organizational-change benchmark using transaction, reorganization, and leadership-transition examples.',
    [
      [
        'primary-coca-cola',
        'Coca-Cola M&A',
        'First transaction benchmark',
        'primary',
      ],
      ['primary-pepsi', 'Pepsi M&A', 'Second transaction benchmark', 'primary'],
      ['related-citi', 'Citi reorganization', 'Bank reorganization benchmark'],
      [
        'related-bank-of-america',
        'Bank of America transition',
        'Leadership-transition benchmark',
      ],
    ],
  ),
];

const fallbackLibrary: DocumentLibrary = {
  root_name: 'documents',
  display_path: './documents',
  documents: [
    ['10001', 'Coca_Cola_MA.docx'],
    ['20001', 'Pepsi_Co_MA.docx'],
    ['30001', 'Bank_of_America_CEO.docx'],
    ['30002', 'Citi_Bank_Reorg.docx'],
  ].map(([clientId, name]) => ({
    document_id: `0001/${clientId}/${name}`,
    name,
    title: name.replace('.docx', '').replaceAll('_', ' '),
    path_parts: ['0001', clientId, name],
    format: 'docx',
  })),
};

const fallbackFiledLibrary: FiledDocumentLibrary = {
  root_name: 'filed_documents',
  display_path: './filed_documents',
  documents: [],
};

const researchWorkflowSteps = [
  { label: 'Search', icon: Search },
  { label: 'Read', icon: BookOpenText },
  { label: 'Synthesize', icon: Sparkles },
  { label: 'Write', icon: FileOutput },
];
const filingWorkflowStep = { label: 'File', icon: Upload };

const leadStatuses: Partial<Record<string, LeadStatus>> = {
  search_started: 'active',
  read_started: 'active',
  read_allowed: 'allowed',
  search_blocked: 'blocked',
  read_blocked: 'blocked',
  search_failed: 'failed',
  read_failed: 'failed',
};

const leadStyles: Record<LeadStatus, string> = {
  idle: 'border-slate-700 text-slate-400',
  active: 'border-cyan-400/60 text-cyan-100',
  allowed: 'border-emerald-400/50 text-slate-300',
  blocked: 'border-rose-400/60 text-rose-200',
  failed: 'border-slate-700 text-slate-400',
};

const activityStatuses: Partial<Record<string, DocumentActivity['status']>> = {
  read_started: 'reading',
  read_allowed: 'allowed',
  read_blocked: 'blocked',
  read_failed: 'failed',
};

const stepIndexes: Record<string, number> = {
  Searching: 0,
  Reading: 1,
  Synthesizing: 2,
  Writing: 3,
  Filing: 4,
};

const connectionDetails: Record<
  ApiState,
  { label: string; color: string; icon: LucideIcon; text: string }
> = {
  connecting: {
    label: 'Connecting to local API',
    color: 'bg-amber-300',
    icon: LoaderCircle,
    text: 'text-amber-300',
  },
  online: {
    label: 'Live API connected',
    color: 'bg-emerald-400',
    icon: Activity,
    text: 'text-slate-400',
  },
  offline: {
    label: 'Local API offline',
    color: 'bg-rose-400',
    icon: AlertCircle,
    text: 'text-rose-300',
  },
};

const toneStyles: Record<
  Tone,
  { badge: string; line: string; panel: string; text: string }
> = {
  idle: {
    badge: 'border-slate-700 bg-slate-950 text-slate-400',
    line: 'border-cyan-400/35',
    panel: 'border-slate-700 bg-slate-950/5',
    text: 'text-slate-300',
  },
  active: {
    badge: 'border-cyan-400/30 bg-cyan-400/10 text-cyan-200',
    line: 'border-cyan-400/35',
    panel: 'border-cyan-400 bg-cyan-400/[0.05]',
    text: 'text-slate-300',
  },
  success: {
    badge: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300',
    line: 'border-emerald-400/50',
    panel: 'border-emerald-400 bg-emerald-400/[0.05]',
    text: 'text-emerald-300',
  },
  warning: {
    badge: 'border-amber-400/30 bg-amber-400/10 text-amber-300',
    line: 'border-amber-400/50',
    panel: 'border-amber-400 bg-amber-400/[0.05]',
    text: 'text-amber-300',
  },
  blocked: {
    badge: 'border-rose-400/30 bg-rose-400/10 text-rose-300',
    line: 'border-rose-400/60',
    panel: 'border-rose-400 bg-rose-400/[0.05]',
    text: 'text-rose-300',
  },
  failed: {
    badge: 'border-orange-400/30 bg-orange-400/10 text-orange-300',
    line: 'border-orange-400/50',
    panel: 'border-orange-400 bg-orange-400/[0.05]',
    text: 'text-orange-300',
  },
};

const eventTitles: Record<string, string> = {
  workflow_starting: 'Launching isolated agent process',
  workflow_started: 'Workflow started',
  search_started: 'Searching document metadata',
  search_empty: 'No matching source found',
  search_blocked: 'Search blocked by OpenBox',
  search_failed: 'Search failed',
  synthesis_started: 'Synthesizing returned evidence',
  synthesis_completed: 'Briefing synthesis completed',
  write_started: 'Writing briefing file',
  write_completed: 'Briefing file written',
  write_blocked: 'Report write blocked by OpenBox',
  write_failed: 'Report write failed',
  upload_started: 'Checking filing destination',
  upload_blocked: 'Filing blocked by OpenBox',
  upload_completed: 'Report committed to client folder',
  upload_failed: 'Filing failed',
  workflow_completed: 'Workflow finished',
  workflow_blocked: 'Workflow blocked by OpenBox',
  workflow_failed: 'Workflow failed',
};

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set('Accept', 'application/json');
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
  });
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      payload && typeof payload === 'object' && 'detail' in payload
        ? payload.detail
        : null;
    const message =
      typeof detail === 'string'
        ? detail
        : detail &&
            typeof detail === 'object' &&
            'message' in detail &&
            typeof detail.message === 'string'
          ? detail.message
          : `Request failed (${response.status})`;
    throw Object.assign(new Error(message), {
      status: response.status,
      payload,
    });
  }
  return payload as T;
}

function valueAsString(value: unknown): string | undefined {
  return typeof value === 'string' && value.length > 0 ? value : undefined;
}

function lastSequence(run: RunSnapshot | null | undefined): number {
  return run?.events.at(-1)?.sequence ?? 0;
}

function timeLabel(timestamp: string): string {
  const date = new Date(timestamp);
  return Number.isNaN(date.valueOf())
    ? ''
    : new Intl.DateTimeFormat(undefined, {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      }).format(date);
}

function statusDetails(run: RunSnapshot | null): {
  label: string;
  tone: Tone;
  icon: LucideIcon;
} {
  if (!run) {
    return { label: 'Idle', tone: 'idle', icon: Circle };
  }
  if (run.status === 'starting' || run.status === 'running') {
    return { label: run.current_step, tone: 'active', icon: LoaderCircle };
  }
  if (run.status === 'completed') {
    return { label: 'Completed', tone: 'success', icon: CheckCircle2 };
  }
  if (run.status === 'completed_with_restrictions') {
    return {
      label: 'Completed with restrictions',
      tone: 'warning',
      icon: TriangleAlert,
    };
  }
  if (run.status === 'blocked') {
    return { label: 'Blocked by OpenBox', tone: 'blocked', icon: LockKeyhole };
  }
  return { label: 'Failed', tone: 'failed', icon: XCircle };
}

function leadState(run: RunSnapshot | null, label: string): LeadStatus {
  if (!run) return 'idle';
  let state: LeadStatus = 'idle';
  for (const event of run.events) {
    if (event.data.lead !== label && event.data.label !== label) continue;
    state = leadStatuses[event.type] || state;
  }
  return state;
}

function eventTone(eventType: string): Tone {
  if (eventType.endsWith('_blocked')) return 'blocked';
  if (eventType.endsWith('_failed')) return 'failed';
  if (eventType === 'search_empty') return 'warning';
  if (eventType === 'read_allowed' || eventType.endsWith('_completed'))
    return 'success';
  if (eventType.endsWith('_started') || eventType.endsWith('_starting'))
    return 'active';
  return 'idle';
}

function eventSummary(event: WorkflowEvent): EventSummary {
  const query = valueAsString(event.data.query);
  const document =
    valueAsString(event.data.title) || valueAsString(event.data.document_id);
  const destination = valueAsString(event.data.destination_document_id);
  const clientName = valueAsString(event.data.client_name);
  const reason = valueAsString(event.data.reason);

  let title = eventTitles[event.type] || event.type.replaceAll('_', ' ');
  switch (event.type) {
    case 'read_started':
      title = `Reading ${document || 'selected document'}`;
      break;
    case 'read_allowed':
      title = `Read allowed · ${document || 'document'}`;
      break;
    case 'read_blocked':
      title = `Read blocked · ${document || 'document'}`;
      break;
    case 'read_failed':
      title = `Read failed · ${document || 'document'}`;
      break;
    case 'upload_started':
      title = `Filing check · ${clientName || 'client folder'}`;
      break;
    case 'upload_blocked':
      title = `Filing blocked · ${clientName || 'client folder'}`;
      break;
    case 'upload_completed':
      title = `Filed · ${clientName || 'client folder'}`;
      break;
    case 'upload_failed':
      title = `Filing failed · ${clientName || 'client folder'}`;
      break;
    default:
      break;
  }

  const detail =
    event.type === 'search_started'
      ? query
      : event.type.endsWith('_blocked') || event.type.endsWith('_failed')
        ? reason
        : event.type.startsWith('upload_')
          ? destination
          : undefined;
  return { title, detail, tone: eventTone(event.type) };
}

function DocumentTree({
  library,
  filedLibrary,
  activities,
  apiState,
}: {
  library: DocumentLibrary;
  filedLibrary: FiledDocumentLibrary;
  activities: Map<string, DocumentActivity[]>;
  apiState: ApiState;
}) {
  return (
    <aside className="flex min-h-0 flex-col border-r border-slate-800 bg-[#0a1221] lg:sticky lg:top-16 lg:h-[calc(100vh-4rem)]">
      <div className="border-b border-slate-800 px-5 py-5">
        <div className="mb-2 flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-100">
            <FolderOpen className="size-4 text-cyan-300" />
            Document library
          </div>
          <Badge className="border-slate-700 bg-slate-900 text-slate-300">
            {library.documents.length} files
          </Badge>
        </div>
        <p className="font-mono text-[10px] text-slate-500">
          {library.display_path}
        </p>
      </div>

      <ScrollArea className="min-h-0 flex-1">
        <div className="px-3 py-4">
          <div className="mb-1 flex items-center gap-2 rounded-md px-2 py-2 text-xs font-medium text-slate-300">
            <ChevronRight className="size-3.5 text-slate-600" />
            <Folder className="size-4 text-cyan-300/80" />
            {library.root_name}
          </div>
          <div className="ml-4 border-l border-slate-800 pl-2">
            <div className="mb-1 flex items-center gap-2 rounded-md px-2 py-2 text-xs text-slate-400">
              <ChevronRight className="size-3.5 text-slate-600" />
              <Folder className="size-4 text-cyan-300/60" />
              0001
            </div>
            <div className="ml-4 space-y-1 border-l border-slate-800 pl-2">
              {library.documents.map((document) => {
                const documentActivities =
                  activities.get(document.document_id) || [];
                const clientId = document.path_parts.at(-2) || '';
                const blocked = documentActivities.filter(
                  (item) => item.status === 'blocked',
                );
                return (
                  <div
                    key={document.document_id}
                    className={cn(
                      'rounded-md border px-2 py-2.5 transition-colors',
                      blocked.length
                        ? 'border-rose-400/25 bg-rose-400/[0.06]'
                        : 'border-transparent hover:border-slate-700 hover:bg-slate-900/80',
                    )}
                  >
                    <div className="flex items-start gap-2">
                      <Folder className="mt-0.5 size-3.5 shrink-0 text-amber-300/70" />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-mono text-[10px] text-slate-500">
                            {clientId}
                          </span>
                          <div
                            className="flex items-center gap-1"
                            aria-label="Agent file activity"
                          >
                            {(['amy', 'barry', 'colin'] as AgentSlug[]).map(
                              (slug) => {
                                const activity = documentActivities.find(
                                  (item) => item.agentSlug === slug,
                                );
                                return (
                                  <span
                                    key={slug}
                                    title={`${slug}: ${activity?.status || 'idle'}`}
                                    className={cn(
                                      'grid size-5 place-items-center rounded-full border text-[8px] font-semibold uppercase',
                                      !activity &&
                                        'border-slate-700 bg-slate-900 text-slate-500',
                                      activity?.status === 'reading' &&
                                        'animate-pulse border-cyan-400/50 bg-cyan-400/15 text-cyan-200',
                                      activity?.status === 'allowed' &&
                                        'border-emerald-400/50 bg-emerald-400/15 text-emerald-300',
                                      activity?.status === 'blocked' &&
                                        'border-rose-400/50 bg-rose-400/15 text-rose-300',
                                      activity?.status === 'failed' &&
                                        'border-orange-400/50 bg-orange-400/15 text-orange-300',
                                    )}
                                  >
                                    {appearance[slug].initials.slice(0, 1)}
                                  </span>
                                );
                              },
                            )}
                          </div>
                        </div>
                        <div className="mt-1 flex items-start gap-2">
                          <FileText className="mt-0.5 size-3.5 shrink-0 text-slate-500" />
                          <div className="min-w-0">
                            <p className="truncate text-xs font-medium text-slate-200">
                              {clientNames[clientId] || document.title}
                            </p>
                            <p className="mt-0.5 truncate font-mono text-[9px] text-slate-600">
                              {document.name}
                            </p>
                          </div>
                        </div>
                        {blocked.map((activity) => (
                          <div
                            key={activity.agentSlug}
                            className="mt-2 border-l border-rose-400/40 pl-2 text-[9px] leading-4 text-rose-300"
                          >
                            <span className="font-semibold capitalize">
                              {activity.agentSlug}
                            </span>
                            {' · '}
                            {activity.reason || 'Blocked by OpenBox'}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="mt-5 border-t border-slate-800 pt-4">
            <div className="mb-1 flex items-center justify-between rounded-md px-2 py-2">
              <div className="flex items-center gap-2 text-xs font-medium text-slate-300">
                <ChevronRight className="size-3.5 text-slate-600" />
                <FolderOpen className="size-4 text-emerald-300/80" />
                Filed reports
              </div>
              <Badge className="border-emerald-400/20 bg-emerald-400/[0.06] text-emerald-300">
                {filedLibrary.documents.length}
              </Badge>
            </div>
            <p className="px-2 font-mono text-[9px] text-slate-600">
              {filedLibrary.display_path}
            </p>
            <div className="ml-4 mt-2 space-y-1 border-l border-slate-800 pl-2">
              {filedLibrary.documents.length === 0 ? (
                <p className="px-2 py-2 text-[10px] leading-4 text-slate-600">
                  Eligible uploads will appear here after barrier checks allow filing.
                </p>
              ) : (
                filedLibrary.documents.map((document) => {
                  const clientId = document.path_parts.at(-2) || '';
                  return (
                    <div
                      key={document.destination_document_id}
                      className="rounded-md border border-emerald-400/15 bg-emerald-400/[0.04] px-2 py-2.5"
                    >
                      <div className="flex items-start gap-2">
                        <FileText className="mt-0.5 size-3.5 shrink-0 text-emerald-300" />
                        <div className="min-w-0">
                          <p className="truncate text-[11px] font-medium text-slate-200">
                            {clientNames[clientId] || clientId}
                          </p>
                          <p className="mt-0.5 truncate font-mono text-[9px] text-slate-500">
                            {document.destination_document_id}
                          </p>
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      </ScrollArea>

      <div className="border-t border-slate-800 px-5 py-4">
        <div className="mb-2 flex items-center gap-2 text-[11px] text-slate-400">
          <LockKeyhole className="size-3.5 text-emerald-400" />
          Reads and filings are evaluated by OpenBox
        </div>
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-[9px] text-slate-600">
          <span className="flex items-center gap-1">
            <span className="size-1.5 rounded-full bg-cyan-300" />
            Reading
          </span>
          <span className="flex items-center gap-1">
            <span className="size-1.5 rounded-full bg-emerald-400" />
            Allowed
          </span>
          <span className="flex items-center gap-1">
            <span className="size-1.5 rounded-full bg-rose-400" />
            Blocked
          </span>
        </div>
        {apiState === 'offline' && (
          <p className="mt-3 text-[10px] leading-4 text-amber-300">
            Start the Python API to load live file activity.
          </p>
        )}
      </div>
    </aside>
  );
}

function LeadMarker({ state }: { state: ReturnType<typeof leadState> }) {
  if (state === 'allowed')
    return <Check className="size-3.5 text-emerald-300" />;
  if (state === 'blocked')
    return <LockKeyhole className="size-3.5 text-rose-300" />;
  if (state === 'failed')
    return <AlertCircle className="size-3.5 text-orange-300" />;
  if (state === 'active')
    return <LoaderCircle className="size-3.5 animate-spin text-cyan-200" />;
  return <Circle className="size-2.5 text-slate-700" />;
}

function FilingAttempts({
  agent,
  run,
}: {
  agent: AgentProfile;
  run: RunSnapshot | null;
}) {
  if (agent.filing_targets.length === 0) return null;
  const results = run?.filing_results || [];

  return (
    <div className="mt-5 border-t border-slate-800 pt-4">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
          Filing attempts
        </span>
        <span className="font-mono text-[9px] text-slate-600">
          all client folders
        </span>
      </div>
      <div className="space-y-2">
        {agent.filing_targets.map((target, index) => {
          const attemptNumber = index + 1;
          const result = results.find(
            (item) => item.attempt_number === attemptNumber,
          );
          const started = Boolean(
            run?.events.some(
              (event) =>
                event.type === 'upload_started' &&
                event.data.attempt_number === attemptNumber,
            ),
          );
          const status = result?.status || (started ? 'checking' : 'queued');
          return (
            <div
              key={`${target.destination_folder_id}-${attemptNumber}`}
              className={cn(
                'border-l px-3 py-2',
                status === 'blocked' && 'border-rose-400/60 bg-rose-400/[0.04]',
                status === 'committed' &&
                  'border-emerald-400/60 bg-emerald-400/[0.04]',
                status === 'failed' &&
                  'border-orange-400/60 bg-orange-400/[0.04]',
                status === 'checking' &&
                  'border-cyan-400/60 bg-cyan-400/[0.04]',
                status === 'queued' && 'border-slate-800',
              )}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-[10px] font-medium text-slate-200">
                    {attemptNumber}. {target.label} · {target.client_name}
                  </p>
                  <p className="mt-0.5 truncate font-mono text-[9px] text-slate-600">
                    {result?.destination_document_id ||
                      target.destination_folder_id}
                  </p>
                </div>
                <span
                  className={cn(
                    'flex shrink-0 items-center gap-1 text-[9px] capitalize',
                    status === 'blocked' && 'text-rose-300',
                    status === 'committed' && 'text-emerald-300',
                    status === 'failed' && 'text-orange-300',
                    status === 'checking' && 'text-cyan-200',
                    status === 'queued' && 'text-slate-600',
                  )}
                >
                  {status === 'committed' && <Check className="size-3" />}
                  {status === 'blocked' && <LockKeyhole className="size-3" />}
                  {status === 'failed' && <AlertCircle className="size-3" />}
                  {status === 'checking' && (
                    <LoaderCircle className="size-3 animate-spin" />
                  )}
                  {status === 'queued' && <Circle className="size-2.5" />}
                  {status}
                </span>
              </div>
              {result?.safe_reason && (
                <p className="mt-1 break-words text-[9px] leading-4 text-slate-400">
                  {result.safe_reason}
                </p>
              )}
              {result?.committed_path && (
                <p
                  className="mt-1 truncate font-mono text-[8px] text-emerald-300/70"
                  title={result.committed_path}
                >
                  {result.committed_path}
                </p>
              )}
              {result?.evaluation_response && (
                <details
                  open
                  className="mt-2 border-t border-slate-800/80 pt-2"
                >
                  <summary className="cursor-pointer text-[9px] font-medium text-cyan-200/80">
                    OpenBox evaluate response
                  </summary>
                  <pre className="mt-1.5 max-h-48 overflow-auto whitespace-pre-wrap break-all rounded bg-slate-950/70 p-2 font-mono text-[8px] leading-4 text-slate-400">
                    {JSON.stringify(result.evaluation_response, null, 2)}
                  </pre>
                </details>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function FinalPanel({ run }: { run: RunSnapshot }) {
  const status = statusDetails(run);
  const blockedEvent = [...run.events]
    .reverse()
    .find((event) => event.type.includes('blocked'));
  const reason = run.final_reason || valueAsString(blockedEvent?.data.reason);
  const unavailable = run.events.findLast(
    (event) => event.type === 'workflow_completed',
  )?.data.unavailable_count;
  const filingResults = run.filing_results || [];
  const blockedFilings = filingResults.filter(
    (result) => result.status === 'blocked',
  ).length;
  const committedFilings = filingResults.filter(
    (result) => result.status === 'committed',
  ).length;

  return (
    <div
      className={cn(
        'mt-4 border-l-2 px-3 py-2.5',
        toneStyles[status.tone].panel,
      )}
    >
      <p
        className={cn(
          'text-[11px] font-semibold',
          toneStyles[status.tone].text,
        )}
      >
        Final status · {status.label}
      </p>
      {typeof unavailable === 'number' && unavailable > 0 && (
        <p className="mt-1 text-[10px] text-slate-400">
          {unavailable} research {unavailable === 1 ? 'lead was' : 'leads were'}{' '}
          unavailable.
        </p>
      )}
      {filingResults.length > 0 && (
        <p className="mt-1 text-[10px] text-slate-300">
          {filingResults.length} attempts · {blockedFilings} blocked ·{' '}
          {committedFilings} committed
        </p>
      )}
      {reason && (
        <p className="mt-1 break-words text-[10px] leading-4 text-slate-300">
          {reason}
        </p>
      )}
      {run.report_path && (
        <p
          className="mt-1.5 truncate font-mono text-[9px] text-slate-500"
          title={run.report_path}
        >
          {run.report_path}
        </p>
      )}
    </div>
  );
}

function AgentCard({
  agent,
  run,
  startError,
  onStart,
}: {
  agent: AgentProfile;
  run: RunSnapshot | null;
  startError?: string;
  onStart: (slug: AgentSlug) => void;
}) {
  const status = statusDetails(run);
  const StatusIcon = status.icon;
  const running = Boolean(run && !terminalStatuses.has(run.status));
  const timeline = run?.events.slice(-8) || [];
  const activeStep = run?.current_step || '';
  const workflowSteps = agent.filing_targets.length
    ? [...researchWorkflowSteps, filingWorkflowStep]
    : researchWorkflowSteps;
  const reachedFiling = Boolean(
    run?.events.some((event) => event.type.startsWith('upload_')),
  );
  const completedStepIndex =
    activeStep === 'Finished'
      ? workflowSteps.length - 1
      : reachedFiling
        ? 4
        : (stepIndexes[activeStep] ?? -1);

  return (
    <Card className="gap-0 border border-slate-800 bg-[#101a2c] py-0 text-slate-100 shadow-[0_18px_48px_rgba(0,0,0,0.18)] ring-0">
      <CardHeader className="border-b border-slate-800 px-5 py-5">
        <div className="flex items-center gap-3">
          <div
            className={cn(
              'grid size-10 place-items-center rounded-lg bg-gradient-to-br text-xs font-bold text-slate-950 shadow-lg',
              appearance[agent.slug].accent,
            )}
          >
            {appearance[agent.slug].initials}
          </div>
          <div className="min-w-0">
            <CardTitle className="text-base font-semibold text-white">
              {agent.display_name}
            </CardTitle>
            <CardDescription className="mt-0.5 truncate text-[11px] text-slate-400">
              {agent.role}
            </CardDescription>
          </div>
        </div>
        <CardAction>
          <Badge
            className={cn(
              'max-w-[160px] border',
              toneStyles[status.tone].badge,
            )}
          >
            <StatusIcon className={cn('size-3', running && 'animate-spin')} />
            <span className="truncate">{status.label}</span>
          </Badge>
        </CardAction>
      </CardHeader>

      <CardContent className="flex flex-1 flex-col px-5 py-5">
        <p className="min-h-[60px] text-xs leading-5 text-slate-300">
          {agent.assignment}
        </p>

        <div className="mt-5">
          <div className="mb-2 flex items-center justify-between text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
            <span>Research route</span>
            <span>{agent.leads.length} leads</span>
          </div>
          <div className="space-y-1.5">
            {agent.leads.map((lead, index) => {
              const state = leadState(run, lead.label);
              return (
                <div
                  key={lead.label}
                  className={cn(
                    'flex items-center gap-2 border-l py-1 pl-3 text-[11px]',
                    leadStyles[state],
                  )}
                >
                  <span className="font-mono text-[9px] text-slate-600">
                    0{index + 1}
                  </span>
                  <span className="min-w-0 flex-1 truncate" title={lead.query}>
                    {lead.purpose}
                  </span>
                  <LeadMarker state={state} />
                </div>
              );
            })}
          </div>
        </div>

        <div className="mt-5 border-t border-slate-800 pt-4">
          <div className="mb-3 flex items-center justify-between">
            <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
              Workflow
            </span>
            <span className="font-mono text-[10px] text-slate-500">
              {run?.progress ?? 0}%
            </span>
          </div>
          <Progress
            value={run?.progress ?? 0}
            className="[&_[data-slot=progress-indicator]]:bg-cyan-300 [&_[data-slot=progress-track]]:bg-slate-800"
          />
          <div
            className={cn(
              'mt-4 grid gap-1',
              agent.filing_targets.length ? 'grid-cols-5' : 'grid-cols-4',
            )}
          >
            {workflowSteps.map(({ label, icon: Icon }, index) => {
              const active =
                activeStep === label ||
                (label === 'Synthesize' && activeStep === 'Synthesizing') ||
                (label === 'File' && activeStep === 'Filing');
              const complete =
                run?.status === 'completed' ||
                run?.status === 'completed_with_restrictions' ||
                completedStepIndex > index;
              return (
                <div
                  key={label}
                  className={cn(
                    'flex flex-col items-center gap-1.5',
                    complete
                      ? 'text-emerald-300'
                      : active
                        ? 'text-cyan-200'
                        : 'text-slate-600',
                  )}
                >
                  <div
                    className={cn(
                      'grid size-7 place-items-center rounded-md border bg-slate-950/50',
                      complete
                        ? 'border-emerald-400/30'
                        : active
                          ? 'border-cyan-400/40'
                          : 'border-slate-800',
                    )}
                  >
                    <Icon
                      className={cn(
                        'size-3.5',
                        active && running && 'animate-pulse',
                      )}
                    />
                  </div>
                  <span className="text-[9px]">{label}</span>
                </div>
              );
            })}
          </div>
        </div>

        <FilingAttempts agent={agent} run={run} />

        {run && timeline.length > 0 && (
          <div className="mt-5 border-t border-slate-800 pt-4">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                Live timeline
              </span>
              <span className="font-mono text-[9px] text-slate-600">
                {run.run_id.slice(0, 8)}
              </span>
            </div>
            <ScrollArea className="h-[150px] pr-2">
              <div className="space-y-2">
                {timeline.map((event) => {
                  const summary = eventSummary(event);
                  return (
                    <div
                      key={event.sequence}
                      className={cn(
                        'border-l pl-2.5',
                        toneStyles[summary.tone].line,
                      )}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <p
                          className={cn(
                            'text-[10px] font-medium leading-4',
                            toneStyles[summary.tone].text,
                          )}
                        >
                          {summary.title}
                        </p>
                        <span className="shrink-0 font-mono text-[8px] text-slate-600">
                          {timeLabel(event.timestamp)}
                        </span>
                      </div>
                      {summary.detail && (
                        <p className="mt-0.5 break-words text-[9px] leading-4 text-slate-500">
                          {summary.detail}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            </ScrollArea>
          </div>
        )}

        {run && terminalStatuses.has(run.status) && <FinalPanel run={run} />}
        {startError && (
          <p className="mt-3 text-[10px] leading-4 text-orange-300">
            {startError}
          </p>
        )}

        <div className="mt-auto pt-5">
          <Button
            className="h-9 w-full bg-cyan-300 font-semibold text-slate-950 hover:bg-cyan-200"
            aria-label={`Start ${agent.display_name}'s workflow`}
            disabled={running}
            onClick={() => onStart(agent.slug)}
          >
            {running ? (
              <LoaderCircle data-icon="inline-start" className="animate-spin" />
            ) : (
              <Play data-icon="inline-start" className="fill-current" />
            )}
            {running
              ? `${run?.current_step || 'Running'}…`
              : run
                ? 'Run again'
                : 'Start workflow'}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export default function Home() {
  const [apiState, setApiState] = useState<ApiState>('connecting');
  const [agents, setAgents] = useState<AgentProfile[]>(fallbackAgents);
  const [library, setLibrary] = useState<DocumentLibrary>(fallbackLibrary);
  const [filedLibrary, setFiledLibrary] =
    useState<FiledDocumentLibrary>(fallbackFiledLibrary);
  const [runs, setRuns] = useState<Partial<Record<AgentSlug, RunSnapshot>>>({});
  const [startErrors, setStartErrors] = useState<
    Partial<Record<AgentSlug, string>>
  >({});
  const streams = useRef<Partial<Record<AgentSlug, EventSource>>>({});

  const mergeRun = useCallback((snapshot: RunSnapshot) => {
    setRuns((current) => {
      const existing = current[snapshot.agent_slug];
      if (
        existing?.run_id === snapshot.run_id &&
        lastSequence(existing) > lastSequence(snapshot)
      ) {
        return current;
      }
      return { ...current, [snapshot.agent_slug]: snapshot };
    });
  }, []);

  const refreshFiledDocuments = useCallback(async () => {
    try {
      const payload = await apiFetch<FiledDocumentLibrary>(
        '/api/filed-documents',
      );
      setFiledLibrary(payload);
    } catch {
      // The run stream remains useful if this display-only refresh fails.
    }
  }, []);

  const refreshRun = useCallback(
    async (agentSlug: AgentSlug, runId: string) => {
      try {
        const snapshot = await apiFetch<RunSnapshot>(`/api/runs/${runId}`);
        mergeRun(snapshot);
        return snapshot;
      } catch {
        setStartErrors((current) => ({
          ...current,
          [agentSlug]: 'The live event stream disconnected. Retrying…',
        }));
        return null;
      }
    },
    [mergeRun],
  );

  const connectStream = useCallback(
    (agentSlug: AgentSlug, run: RunSnapshot) => {
      streams.current[agentSlug]?.close();
      if (terminalStatuses.has(run.status)) return;

      const source = new EventSource(
        `${API_BASE}/api/runs/${run.run_id}/events?after=${lastSequence(run)}`,
      );
      streams.current[agentSlug] = source;
      source.onopen = () => {
        setApiState('online');
        setStartErrors((current) => ({ ...current, [agentSlug]: undefined }));
      };
      source.onmessage = (message) => {
        try {
          const event = JSON.parse(message.data) as WorkflowEvent;
          void refreshRun(agentSlug, run.run_id);
          if (event.type === 'upload_completed') {
            void refreshFiledDocuments();
          }
          if (terminalEvents.has(event.type)) {
            source.close();
            delete streams.current[agentSlug];
          }
        } catch {
          return;
        }
      };
    },
    [refreshFiledDocuments, refreshRun],
  );

  useEffect(() => {
    let cancelled = false;
    const activeStreams = streams.current;
    async function bootstrap() {
      try {
        const [agentPayload, documentPayload, filedDocumentPayload] =
          await Promise.all([
            apiFetch<{ agents: AgentProfile[] }>('/api/agents'),
            apiFetch<DocumentLibrary>('/api/documents'),
            apiFetch<FiledDocumentLibrary>('/api/filed-documents'),
          ]);
        if (cancelled) return;
        setAgents(agentPayload.agents);
        setLibrary(documentPayload);
        setFiledLibrary(filedDocumentPayload);
        setApiState('online');
        for (const agent of agentPayload.agents) {
          if (!agent.latest_run) continue;
          mergeRun(agent.latest_run);
          connectStream(agent.slug, agent.latest_run);
        }
      } catch {
        if (!cancelled) setApiState('offline');
      }
    }
    void bootstrap();
    return () => {
      cancelled = true;
      for (const source of Object.values(activeStreams)) source?.close();
    };
  }, [connectStream, mergeRun]);

  async function startWorkflow(agentSlug: AgentSlug) {
    setStartErrors({ ...startErrors, [agentSlug]: undefined });
    try {
      const run = await apiFetch<RunSnapshot>(`/api/agents/${agentSlug}/runs`, {
        method: 'POST',
      });
      setApiState('online');
      mergeRun(run);
      connectStream(agentSlug, run);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : 'Could not start the workflow';
      setStartErrors({ ...startErrors, [agentSlug]: message });
      if ((error as { status?: number }).status !== 409) setApiState('offline');
    }
  }

  const documentActivities = useMemo(() => {
    const activityMap = new Map<string, Map<AgentSlug, DocumentActivity>>();
    for (const [slug, run] of Object.entries(runs) as [
      AgentSlug,
      RunSnapshot,
    ][]) {
      if (!run) continue;
      for (const event of run.events) {
        const documentId = valueAsString(event.data.document_id);
        const status = activityStatuses[event.type];
        if (!documentId || !status) continue;
        const perAgent =
          activityMap.get(documentId) || new Map<AgentSlug, DocumentActivity>();
        const activity: DocumentActivity = { agentSlug: slug, status };
        if (status === 'blocked' || status === 'failed') {
          activity.reason = valueAsString(event.data.reason);
        }
        perAgent.set(slug, activity);
        activityMap.set(documentId, perAgent);
      }
    }
    return new Map(
      [...activityMap.entries()].map(([documentId, perAgent]) => [
        documentId,
        [...perAgent.values()],
      ]),
    );
  }, [runs]);

  const connection = connectionDetails[apiState];
  const ConnectionIcon = connection.icon;

  return (
    <main className="min-h-screen bg-[#07101d] text-slate-100">
      <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-slate-800 bg-[#0a1322]/95 px-5 backdrop-blur lg:px-7">
        <div className="flex items-center gap-3">
          <div className="grid size-9 place-items-center rounded-lg border border-cyan-300/20 bg-cyan-300/10">
            <ShieldCheck className="size-5 text-cyan-300" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-sm font-semibold tracking-tight text-white">
                OpenBox Barrier Demo
              </h1>
              <span className="hidden text-[10px] font-medium uppercase tracking-[0.16em] text-slate-600 sm:inline">
                OpenBox protected
              </span>
            </div>
            <p className="mt-0.5 text-[10px] text-slate-500">
              LangGraph research workflows · local operator view
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div
            className={cn(
              'hidden items-center gap-2 text-[11px] sm:flex',
              connection.text,
            )}
          >
            <ConnectionIcon
              className={cn(
                'size-3.5',
                apiState === 'connecting' && 'animate-spin',
              )}
            />
            {connection.label}
          </div>
          <Badge className="border-slate-700 bg-slate-950 text-slate-300">
            <span className={cn('size-1.5 rounded-full', connection.color)} />
            Local
          </Badge>
        </div>
      </header>

      <div className="grid min-h-[calc(100vh-4rem)] grid-cols-1 lg:grid-cols-[320px_minmax(0,1fr)]">
        <DocumentTree
          library={library}
          filedLibrary={filedLibrary}
          activities={documentActivities}
          apiState={apiState}
        />

        <section className="min-w-0 bg-[radial-gradient(circle_at_top_right,rgba(34,211,238,0.07),transparent_34%)] px-4 py-6 sm:px-6 lg:px-8 lg:py-7">
          <div className="mx-auto max-w-[1480px]">
            <div className="mb-5 flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
              <div>
                <div className="mb-2 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-cyan-300">
                  <Building2 className="size-3.5" />
                  Research operations
                </div>
                <h2 className="text-xl font-semibold tracking-tight text-white">
                  Agent workflows
                </h2>
                <p className="mt-1 max-w-2xl text-xs leading-5 text-slate-400">
                  Start any agent independently. Research, report writing, and
                  governed filing decisions appear here as they happen.
                </p>
              </div>
              <div className="flex items-center gap-2 text-[10px] text-slate-500">
                <CheckCircle2 className="size-3.5 text-emerald-400" />
                Credentials stay in the Python service
              </div>
            </div>

            {apiState === 'offline' && (
              <div className="mb-4 flex items-start gap-2 border-l-2 border-amber-400 bg-amber-400/[0.06] px-3 py-2.5 text-[11px] leading-5 text-amber-200">
                <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
                The dashboard is visible, but workflows need the local Python
                API. Run{' '}
                <span className="font-mono">
                  uv run barrier-web
                </span>{' '}
                from the project folder.
              </div>
            )}

            <div className="grid items-start gap-4 xl:grid-cols-3">
              {agents.map((agent) => (
                <AgentCard
                  key={agent.slug}
                  agent={agent}
                  run={runs[agent.slug] || null}
                  startError={startErrors[agent.slug]}
                  onStart={startWorkflow}
                />
              ))}
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
