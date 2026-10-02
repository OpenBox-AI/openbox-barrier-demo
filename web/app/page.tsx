'use client';

import {
  Activity,
  AlertCircle,
  BookOpenText,
  Check,
  CheckCircle2,
  ChevronRight,
  Circle,
  Clock,
  FileOutput,
  FileText,
  FolderOpen,
  LoaderCircle,
  LockKeyhole,
  Play,
  ScrollText,
  Search,
  Sparkles,
  TriangleAlert,
  type LucideIcon,
  Upload,
  XCircle,
} from 'lucide-react';
import {
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { OpenBoxLogo } from '@/components/ui/openbox-logo';
import {
  Card,
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
  | 'awaiting_approval'
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
type Tone =
  | 'idle'
  | 'active'
  | 'approval'
  | 'success'
  | 'warning'
  | 'blocked'
  | 'failed';
type LeadStatus =
  | 'idle'
  | 'active'
  | 'awaiting'
  | 'allowed'
  | 'blocked'
  | 'failed';

type DocumentActivity = {
  agentSlug: AgentSlug;
  status: 'reading' | 'awaiting' | 'allowed' | 'blocked' | 'failed';
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

const appearance: Record<AgentSlug, { initials: string }> = {
  amy: { initials: 'AM' },
  barry: { initials: 'BA' },
  colin: { initials: 'CO' },
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
  approval_requested: 'awaiting',
  read_allowed: 'allowed',
  search_blocked: 'blocked',
  read_blocked: 'blocked',
  search_failed: 'failed',
  read_failed: 'failed',
};

const leadStyles: Record<LeadStatus, string> = {
  idle: 'border-border text-gray-700',
  active: 'border-dodger-blue-400 text-gray-900',
  awaiting: 'border-tier-2 text-tier-2-text',
  allowed: 'border-tier-1 text-gray-700',
  blocked: 'border-tier-3 text-tier-3-text',
  failed: 'border-tier-4 text-tier-4-text',
};

const activityStatuses: Partial<Record<string, DocumentActivity['status']>> = {
  read_started: 'reading',
  approval_requested: 'awaiting',
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
    color: 'bg-tier-3',
    icon: LoaderCircle,
    text: 'text-tier-3-text',
  },
  online: {
    label: 'Live API connected',
    color: 'bg-tier-1',
    icon: Activity,
    text: 'text-muted-foreground',
  },
  offline: {
    label: 'Local API offline',
    color: 'bg-tier-3',
    icon: AlertCircle,
    text: 'text-tier-3-text',
  },
};

const toneStyles: Record<
  Tone,
  { badge: string; line: string; panel: string; text: string }
> = {
  idle: {
    badge: 'border-transparent bg-muted text-muted-foreground',
    line: 'border-border',
    panel: 'border-border bg-muted',
    text: 'text-gray-900',
  },
  active: {
    badge: 'border-transparent bg-dodger-blue-50 text-dodger-blue-700',
    line: 'border-dodger-blue-300',
    panel: 'border-dodger-blue-400 bg-dodger-blue-50',
    text: 'text-gray-900',
  },
  // OpenBox shows REQUIRE_APPROVAL in the info tier.
  approval: {
    badge: 'border-transparent bg-tier-2-badge text-tier-2-text',
    line: 'border-tier-2',
    panel: 'border-tier-2 bg-tier-2-badge/40',
    text: 'text-tier-2-text',
  },
  success: {
    badge: 'border-transparent bg-tier-1-badge text-tier-1-text',
    line: 'border-tier-1',
    panel: 'border-tier-1 bg-tier-1-badge/40',
    text: 'text-tier-1-text',
  },
  // OpenBox renders BLOCK in the warning tier and HALT/errors in red.
  warning: {
    badge: 'border-transparent bg-tier-3-badge text-tier-3-text',
    line: 'border-tier-3',
    panel: 'border-tier-3 bg-tier-3-badge/40',
    text: 'text-tier-3-text',
  },
  blocked: {
    badge: 'border-transparent bg-tier-3-badge text-tier-3-text',
    line: 'border-tier-3',
    panel: 'border-tier-3 bg-tier-3-badge/40',
    text: 'text-tier-3-text',
  },
  failed: {
    badge: 'border-transparent bg-tier-4-badge text-tier-4-text',
    line: 'border-tier-4',
    panel: 'border-tier-4 bg-tier-4-badge/40',
    text: 'text-tier-4-text',
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
  if (run.status === 'awaiting_approval') {
    return { label: 'Requires approval', tone: 'approval', icon: Clock };
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

function clientIdOf(path: string | undefined): string {
  return path?.split('/')[1] ?? '';
}

// Absolute paths from the API are long; show them from the project's data folder down.
function shortPath(path: string): string {
  for (const marker of ['/filed_documents/', '/output/']) {
    const index = path.lastIndexOf(marker);
    if (index >= 0) return path.slice(index + 1);
  }
  return path.split('/').slice(-3).join('/');
}

function eventTone(eventType: string): Tone {
  if (eventType === 'approval_requested') return 'approval';
  if (eventType === 'approval_granted') return 'success';
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
    case 'approval_requested':
      title = `Approval needed · ${clientName || document || 'this step'}`;
      break;
    case 'approval_granted':
      title = 'Approved · the run continues';
      break;
    default:
      break;
  }

  const detail =
    event.type === 'search_started'
      ? query
      : event.type.endsWith('_blocked') ||
          event.type.endsWith('_failed') ||
          event.type === 'approval_requested'
        ? reason
        : event.type.startsWith('upload_')
          ? destination
          : undefined;
  return { title, detail, tone: eventTone(event.type) };
}

const activityDot: Record<DocumentActivity['status'] | 'idle', string> = {
  idle: 'border-border bg-muted text-gray-500',
  reading:
    'border-dodger-blue-300 bg-dodger-blue-50 text-dodger-blue-600 motion-safe:animate-pulse',
  awaiting: 'border-tier-2 bg-tier-2 text-white',
  allowed: 'border-tier-1/50 bg-tier-1-badge/40 text-tier-1-text',
  blocked: 'border-tier-3/50 bg-tier-3-badge/50 text-tier-3-text',
  failed: 'border-tier-4/50 bg-tier-4-badge/50 text-tier-4-text',
};

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
    <aside className="order-last flex min-h-0 flex-col border-t border-border bg-white lg:sticky lg:top-16 lg:order-none lg:h-[calc(100vh-4rem)] lg:border-t-0 lg:border-r">
      <div className="border-b border-border px-5 py-4">
        <div className="flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-gray-900">
            <FolderOpen className="size-4 text-dodger-blue-600" />
            Document library
          </h2>
          <span className="text-xs text-muted-foreground">
            {library.documents.length} files
          </span>
        </div>
        <p className="mt-1 font-mono text-[11px] text-gray-500">
          {library.display_path}/0001
        </p>
      </div>

      <ScrollArea className="min-h-0 flex-1">
        <div className="space-y-1.5 px-3 py-3">
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
                  'rounded-md border px-3 py-2.5',
                  blocked.length
                    ? 'border-tier-3/50 bg-tier-3-badge/50'
                    : 'border-border',
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <FileText className="size-4 shrink-0 text-gray-500" />
                    <p className="truncate text-sm font-medium text-gray-900">
                      {clientNames[clientId] || document.title}
                    </p>
                  </div>
                  <div
                    className="flex items-center gap-1"
                    aria-label="Agent reads of this document"
                  >
                    {(['amy', 'barry', 'colin'] as AgentSlug[]).map((slug) => {
                      const activity = documentActivities.find(
                        (item) => item.agentSlug === slug,
                      );
                      const state = activity?.status || 'idle';
                      return (
                        <span
                          key={slug}
                          title={`${slug[0].toUpperCase()}${slug.slice(1)}: ${state === 'idle' ? 'not read' : state}`}
                          className={cn(
                            'grid size-6 place-items-center rounded-full border text-[10px] font-semibold',
                            activityDot[state],
                          )}
                        >
                          {appearance[slug].initials.slice(0, 1)}
                        </span>
                      );
                    })}
                  </div>
                </div>
                <p className="mt-1 truncate pl-6 font-mono text-[11px] text-gray-500">
                  {clientId}/{document.name}
                </p>
                {blocked.map((activity) => (
                  <p
                    key={activity.agentSlug}
                    className="mt-2 ml-6 border-l border-tier-3/50 pl-2 text-xs leading-4 text-tier-3-text"
                  >
                    <span className="font-semibold capitalize">
                      {activity.agentSlug}:
                    </span>{' '}
                    {activity.reason || 'Blocked by OpenBox'}
                  </p>
                ))}
              </div>
            );
          })}

          <div className="mt-4 border-t border-border px-2 pt-4">
            <div className="flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-gray-900">
                <FolderOpen className="size-4 text-tier-1-text" />
                Filed reports
              </h2>
              <span className="text-xs text-muted-foreground">
                {filedLibrary.documents.length}
              </span>
            </div>
            <p className="mt-1 font-mono text-[11px] text-gray-500">
              {filedLibrary.display_path}
            </p>
          </div>
          {filedLibrary.documents.length === 0 ? (
            <p className="px-2 py-2 text-xs leading-5 text-gray-500">
              Nothing filed yet. Reports appear here when OpenBox allows an
              upload.
            </p>
          ) : (
            filedLibrary.documents.map((document) => {
              const clientId = document.path_parts.at(-2) || '';
              return (
                <div
                  key={document.destination_document_id}
                  className="flex items-start gap-2 rounded-md border border-tier-1/50 bg-tier-1-badge/40 px-3 py-2"
                >
                  <FileText className="mt-0.5 size-4 shrink-0 text-tier-1-text" />
                  <div className="min-w-0">
                    <p className="truncate text-sm text-gray-900">
                      {clientNames[clientId] || clientId}
                    </p>
                    <p className="truncate font-mono text-[11px] text-gray-500">
                      {document.name}
                    </p>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </ScrollArea>

      <div className="border-t border-border px-5 py-3">
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-primary" />
            Reading
          </span>
          <span className="flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-tier-2" />
            Requires approval
          </span>
          <span className="flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-tier-1" />
            Allowed
          </span>
          <span className="flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-tier-3" />
            Blocked
          </span>
        </div>
        {apiState === 'offline' && (
          <p className="mt-2 text-xs leading-5 text-tier-3-text">
            Start the Python API to load live file activity.
          </p>
        )}
      </div>
    </aside>
  );
}

type CellState =
  | 'none'
  | 'reading'
  | 'allowed'
  | 'checking'
  | 'awaiting'
  | 'queued'
  | 'filed'
  | 'blocked'
  | 'failed';

const cellDetails: Record<
  CellState,
  { label: string; icon: LucideIcon; className: string }
> = {
  none: { label: 'Not used', icon: Circle, className: 'text-gray-400' },
  reading: {
    label: 'Reading',
    icon: LoaderCircle,
    className: 'text-dodger-blue-600',
  },
  allowed: {
    label: 'Allowed',
    icon: Check,
    className: 'bg-tier-1-badge/40 text-tier-1-text',
  },
  checking: {
    label: 'Checking',
    icon: LoaderCircle,
    className: 'text-dodger-blue-600',
  },
  awaiting: {
    label: 'Requires approval',
    icon: Clock,
    className: 'bg-tier-2-badge/60 text-tier-2-text',
  },
  queued: { label: 'Queued', icon: Circle, className: 'text-gray-500' },
  filed: {
    label: 'Filed',
    icon: Check,
    className: 'bg-tier-1-badge/40 text-tier-1-text',
  },
  blocked: {
    label: 'Blocked',
    icon: LockKeyhole,
    className: 'bg-tier-3-badge/50 text-tier-3-text',
  },
  failed: {
    label: 'Failed',
    icon: AlertCircle,
    className: 'bg-tier-4-badge/50 text-tier-4-text',
  },
};

function readCell(
  run: RunSnapshot | null,
  clientId: string,
): { state: CellState; reason?: string } {
  let cell: { state: CellState; reason?: string } = { state: 'none' };
  for (const event of run?.events || []) {
    const status = activityStatuses[event.type];
    if (!status) continue;
    if (clientIdOf(valueAsString(event.data.document_id)) !== clientId)
      continue;
    cell = {
      state: status,
      reason: valueAsString(event.data.reason),
    };
  }
  return cell;
}

function fileCell(
  run: RunSnapshot | null,
  clientId: string,
): { state: CellState; reason?: string } {
  if (!run) return { state: 'none' };
  const result = run.filing_results.find(
    (item) => clientIdOf(item.destination_document_id) === clientId,
  );
  if (result) {
    return {
      state: result.status === 'committed' ? 'filed' : result.status,
      reason: result.safe_reason || undefined,
    };
  }
  let pending: { state: CellState; reason?: string } | null = null;
  for (const event of run.events) {
    const destination = valueAsString(event.data.destination_document_id);
    if (clientIdOf(destination) !== clientId) continue;
    if (event.type === 'upload_started') pending = { state: 'checking' };
    if (event.type === 'approval_requested') {
      pending = { state: 'awaiting', reason: valueAsString(event.data.reason) };
    }
  }
  if (pending) return pending;
  return terminalStatuses.has(run.status)
    ? { state: 'none' }
    : { state: 'queued' };
}

function OutcomeCell({
  cell,
}: {
  cell: { state: CellState; reason?: string };
}) {
  const details = cellDetails[cell.state];
  const Icon = details.icon;
  const inProgress = cell.state === 'reading' || cell.state === 'checking';
  return (
    <td
      className={cn('border-l border-border px-3 py-2', details.className)}
      title={cell.reason}
    >
      <span className="flex items-center gap-1.5 text-xs font-medium">
        <Icon
          className={cn('size-3.5 shrink-0', inProgress && 'animate-spin')}
        />
        {details.label}
      </span>
    </td>
  );
}

function OutcomeMatrix({
  agents,
  runs,
  library,
}: {
  agents: AgentProfile[];
  runs: Partial<Record<AgentSlug, RunSnapshot>>;
  library: DocumentLibrary;
}) {
  const clientIds = [
    ...new Set(library.documents.map((item) => item.path_parts.at(-2) || '')),
  ].filter(Boolean);

  return (
    <div className="overflow-x-auto rounded-xl border border-border bg-card">
      <table className="w-full min-w-[640px] border-collapse text-left">
        <caption className="sr-only">
          OpenBox decision for each agent and client folder
        </caption>
        <thead>
          <tr className="border-b border-border text-xs text-muted-foreground">
            <th scope="col" className="px-4 py-2.5 font-medium">
              Agent
            </th>
            <th scope="col" className="px-3 py-2.5 font-medium">
              <span className="sr-only">Action</span>
            </th>
            {clientIds.map((clientId) => (
              <th
                key={clientId}
                scope="col"
                className="border-l border-border px-3 py-2.5 font-medium text-gray-800"
              >
                {clientNames[clientId] || clientId}
                <span className="ml-1.5 font-mono text-[11px] font-normal text-gray-500">
                  {clientId}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        {agents.map((agent) => {
          const run = runs[agent.slug] || null;
          const files = agent.filing_targets.length > 0;
          return (
            <tbody
              key={agent.slug}
              className="border-b border-border last:border-b-0"
            >
              <tr>
                <th
                  scope="rowgroup"
                  rowSpan={2}
                  aria-label={agent.display_name}
                  className="px-4 py-2 align-middle"
                >
                  <span className="flex items-center gap-2.5">
                    <span
                      className={cn(
                        'grid size-7 shrink-0 place-items-center rounded-lg bg-dodger-blue-100 text-[11px] font-semibold text-dodger-blue-700',
                      )}
                    >
                      {appearance[agent.slug].initials}
                    </span>
                    <span className="text-sm font-semibold text-gray-950">
                      {agent.display_name}
                    </span>
                  </span>
                </th>
                <th
                  scope="row"
                  className="px-3 py-2 text-xs font-normal text-muted-foreground"
                >
                  Read
                </th>
                {clientIds.map((clientId) => (
                  <OutcomeCell key={clientId} cell={readCell(run, clientId)} />
                ))}
              </tr>
              <tr className="border-t border-border">
                <th
                  scope="row"
                  className="px-3 py-2 text-xs font-normal text-muted-foreground"
                >
                  File
                </th>
                {files ? (
                  clientIds.map((clientId) => (
                    <OutcomeCell
                      key={clientId}
                      cell={fileCell(run, clientId)}
                    />
                  ))
                ) : (
                  <td
                    colSpan={clientIds.length}
                    className="border-l border-border px-3 py-2 text-xs text-gray-500"
                  >
                    No filing step: this report covers several clients.
                  </td>
                )}
              </tr>
            </tbody>
          );
        })}
      </table>
    </div>
  );
}

function LeadMarker({ state }: { state: ReturnType<typeof leadState> }) {
  if (state === 'allowed')
    return <Check className="size-3.5 text-tier-1-text" aria-label="Allowed" />;
  if (state === 'blocked')
    return (
      <LockKeyhole className="size-3.5 text-tier-3-text" aria-label="Blocked" />
    );
  if (state === 'failed')
    return (
      <AlertCircle className="size-3.5 text-tier-4-text" aria-label="Failed" />
    );
  if (state === 'awaiting')
    return (
      <Clock
        className="size-3.5 text-tier-2-text"
        aria-label="Requires approval"
      />
    );
  if (state === 'active')
    return (
      <LoaderCircle
        className="size-3.5 animate-spin text-dodger-blue-600"
        aria-label="In progress"
      />
    );
  return <Circle className="size-2.5 text-gray-300" />;
}

const filingStatusDetails: Record<
  FilingResult['status'] | 'checking' | 'awaiting' | 'queued',
  { label: string; icon: LucideIcon; text: string; border: string }
> = {
  committed: {
    label: 'Filed',
    icon: Check,
    text: 'text-tier-1-text',
    border: 'border-tier-1/50',
  },
  blocked: {
    label: 'Blocked',
    icon: LockKeyhole,
    text: 'text-tier-3-text',
    border: 'border-tier-3/50',
  },
  failed: {
    label: 'Failed',
    icon: AlertCircle,
    text: 'text-tier-4-text',
    border: 'border-tier-4/50',
  },
  checking: {
    label: 'Checking',
    icon: LoaderCircle,
    text: 'text-dodger-blue-600 [&>svg]:animate-spin',
    border: 'border-dodger-blue-300',
  },
  awaiting: {
    label: 'Requires approval',
    icon: Clock,
    text: 'text-tier-2-text',
    border: 'border-tier-2',
  },
  queued: {
    label: 'Queued',
    icon: Circle,
    text: 'text-gray-500',
    border: 'border-border',
  },
};

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
    <section className="mt-5 border-t border-border pt-4">
      <h3 className="mb-2 text-xs font-medium text-muted-foreground">
        Filing, in order, to every client folder
      </h3>
      <ol className="space-y-1.5">
        {agent.filing_targets.map((target, index) => {
          const attemptNumber = index + 1;
          const result = results.find(
            (item) => item.attempt_number === attemptNumber,
          );
          const lastEvent = run?.events.findLast(
            (event) =>
              (event.type === 'upload_started' ||
                event.type === 'approval_requested') &&
              event.data.attempt_number === attemptNumber,
          );
          const status =
            result?.status ||
            (lastEvent?.type === 'approval_requested'
              ? 'awaiting'
              : lastEvent
                ? 'checking'
                : 'queued');
          const details = filingStatusDetails[status];
          const StatusIcon = details.icon;
          return (
            <li
              key={`${target.destination_folder_id}-${attemptNumber}`}
              className={cn('border-l-2 py-1.5 pr-1 pl-3', details.border)}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-sm text-gray-900">
                    <span className="mr-1.5 text-gray-500">
                      {attemptNumber}
                    </span>
                    {target.client_name}
                  </p>
                  <p
                    className="truncate font-mono text-[11px] text-gray-500"
                    title={result?.committed_path || undefined}
                  >
                    {result?.destination_document_id ||
                      target.destination_folder_id}
                  </p>
                </div>
                <span
                  className={cn(
                    'flex shrink-0 items-center gap-1 text-xs font-medium [&>svg]:size-3.5',
                    details.text,
                  )}
                >
                  <StatusIcon />
                  {details.label}
                </span>
              </div>
              {result?.safe_reason && (
                <p className="mt-1 text-xs leading-5 break-words text-gray-600">
                  {result.safe_reason}
                </p>
              )}
              {result?.evaluation_response && (
                <details className="group mt-1">
                  <summary className="flex w-fit cursor-pointer list-none items-center gap-1 rounded text-xs text-dodger-blue-600 hover:text-dodger-blue-700 [&::-webkit-details-marker]:hidden">
                    <ChevronRight className="size-3.5 transition-transform group-open:rotate-90 motion-reduce:transition-none" />
                    OpenBox response
                  </summary>
                  <pre className="mt-1.5 max-h-56 overflow-auto rounded-md bg-muted p-2.5 font-mono text-[11px] leading-4 break-all whitespace-pre-wrap text-gray-600">
                    {JSON.stringify(result.evaluation_response, null, 2)}
                  </pre>
                </details>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function Timeline({ run }: { run: RunSnapshot }) {
  const viewport = useRef<HTMLDivElement>(null);
  const count = run.events.length;

  // Keep the newest event in view as the run streams in.
  useEffect(() => {
    const node = viewport.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [count]);

  return (
    <section className="mt-5 border-t border-border pt-4">
      <h3 className="mb-2 flex items-center justify-between text-xs font-medium text-muted-foreground">
        Live timeline
        <span className="font-mono text-[11px] font-normal text-gray-400">
          run {run.run_id.slice(0, 8)}
        </span>
      </h3>
      <div
        ref={viewport}
        className="max-h-48 space-y-2 overflow-y-auto pr-2"
        aria-live="polite"
      >
        {run.events.map((event) => {
          const summary = eventSummary(event);
          return (
            <div
              key={event.sequence}
              className={cn('border-l-2 pl-2.5', toneStyles[summary.tone].line)}
            >
              <div className="flex items-start justify-between gap-2">
                <p
                  className={cn(
                    'text-xs leading-5 font-medium',
                    toneStyles[summary.tone].text,
                  )}
                >
                  {summary.title}
                </p>
                <span className="shrink-0 font-mono text-[11px] leading-5 text-gray-400">
                  {timeLabel(event.timestamp)}
                </span>
              </div>
              {summary.detail && (
                <p className="text-xs leading-5 break-words text-muted-foreground">
                  {summary.detail}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

// Minimal Markdown for the generated briefing: headings, bullets, paragraphs.
// Rendered as React elements, never as HTML, because the text comes from the model.
function Briefing({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  let bullets: string[] = [];
  let paragraph: string[] = [];
  const flush = () => {
    if (paragraph.length) {
      blocks.push(
        <p key={blocks.length} className="text-sm leading-6 text-gray-800">
          {paragraph.join(' ')}
        </p>,
      );
      paragraph = [];
    }
    if (bullets.length) {
      blocks.push(
        <ul
          key={blocks.length}
          className="list-disc space-y-1 pl-5 text-sm leading-6 text-gray-800"
        >
          {bullets.map((item, index) => (
            <li key={index}>{item}</li>
          ))}
        </ul>,
      );
      bullets = [];
    }
  };
  for (const raw of text.split('\n')) {
    const line = raw.trim();
    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    const bullet = /^[-*]\s+(.*)$/.exec(line);
    if (!line) {
      flush();
    } else if (heading) {
      flush();
      blocks.push(
        heading[1].length === 1 ? (
          <h4
            key={blocks.length}
            className="text-base font-semibold text-gray-950"
          >
            {heading[2]}
          </h4>
        ) : (
          <h5
            key={blocks.length}
            className="pt-1 text-sm font-semibold text-gray-900"
          >
            {heading[2]}
          </h5>
        ),
      );
    } else if (bullet) {
      if (paragraph.length) flush();
      bullets.push(bullet[1]);
    } else {
      if (bullets.length) flush();
      paragraph.push(line);
    }
  }
  flush();
  return <div className="space-y-2.5">{blocks}</div>;
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
  const facts = [
    typeof unavailable === 'number' && unavailable > 0
      ? `${unavailable} research ${unavailable === 1 ? 'lead was' : 'leads were'} unavailable.`
      : null,
    filingResults.length > 0
      ? `Filed to ${committedFilings} of ${filingResults.length} folders, ${blockedFilings} blocked.`
      : null,
  ].filter(Boolean);

  return (
    <section
      className={cn(
        'mt-5 rounded-r-md border-l-2 px-3 py-3',
        toneStyles[status.tone].panel,
      )}
    >
      <p className={cn('text-sm font-semibold', toneStyles[status.tone].text)}>
        {status.label}
      </p>
      {facts.map((fact) => (
        <p key={fact} className="mt-1 text-xs leading-5 text-gray-600">
          {fact}
        </p>
      ))}
      {reason && (
        <p className="mt-1 text-xs leading-5 break-words text-gray-600">
          {reason}
        </p>
      )}
      {run.report && (
        <details className="group mt-3 border-t border-border pt-2">
          <summary className="flex w-fit cursor-pointer list-none items-center gap-1.5 rounded text-sm font-medium text-dodger-blue-600 hover:text-dodger-blue-700 [&::-webkit-details-marker]:hidden">
            <ScrollText className="size-4" />
            Read the briefing
            <ChevronRight className="size-3.5 transition-transform group-open:rotate-90 motion-reduce:transition-none" />
          </summary>
          <div className="mt-3 rounded-md border border-border bg-white p-4">
            <Briefing text={run.report} />
          </div>
        </details>
      )}
      {run.report_path && (
        <p
          className="mt-2 truncate font-mono text-[11px] text-gray-500"
          title={run.report_path}
        >
          {shortPath(run.report_path)}
        </p>
      )}
    </section>
  );
}

function ApprovalBanner({ event }: { event: WorkflowEvent }) {
  const target =
    valueAsString(event.data.client_name) ||
    valueAsString(event.data.title) ||
    valueAsString(event.data.document_id);
  const action = event.data.destination_document_id ? 'File to' : 'Read';
  const reason = valueAsString(event.data.reason);
  return (
    <div
      className="shrink-0 border-b border-tier-2/30 bg-tier-2-badge/50 px-5 py-3"
      aria-live="polite"
    >
      <p className="flex items-center gap-2 text-sm font-semibold text-tier-2-text">
        <Clock className="size-4 shrink-0" />
        {target
          ? `${action} ${target}: requires approval`
          : 'Requires approval'}
      </p>
      {reason && (
        <p className="mt-1 text-xs leading-5 break-words text-gray-700">
          {reason}
        </p>
      )}
      <p className="mt-1 text-xs leading-5 text-gray-600">
        Approve or reject it in OpenBox. If approved, the run continues from
        this step.
      </p>
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
  const awaitingApproval = run?.status === 'awaiting_approval';
  const approvalRequest = awaitingApproval
    ? run?.events.findLast((event) => event.type === 'approval_requested')
    : undefined;
  // While OpenBox waits, keep the step that asked for approval highlighted.
  const activeStep = approvalRequest
    ? approvalRequest.data.destination_document_id
      ? 'Filing'
      : 'Reading'
    : run?.current_step || '';
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
    <Card className="h-[44rem] gap-0 rounded-lg border border-border bg-card py-0 text-gray-900 shadow-xs ring-0">
      <CardHeader className="border-b border-border px-5 py-4">
        <div className="flex items-center gap-3">
          <div
            className={cn(
              'grid size-10 shrink-0 place-items-center rounded-lg bg-dodger-blue-100 text-sm font-semibold text-dodger-blue-700',
            )}
          >
            {appearance[agent.slug].initials}
          </div>
          <div className="min-w-0">
            <CardTitle className="text-base font-semibold text-gray-950">
              {agent.display_name}
            </CardTitle>
            <CardDescription className="text-xs text-muted-foreground">
              {agent.role}
            </CardDescription>
          </div>
        </div>
        <Badge
          className={cn(
            'mt-3 h-6 border px-2.5',
            toneStyles[status.tone].badge,
          )}
        >
          <StatusIcon
            className={cn(running && !awaitingApproval && 'animate-spin')}
          />
          {status.label}
        </Badge>
      </CardHeader>

      {approvalRequest && <ApprovalBanner event={approvalRequest} />}

      <CardContent
        className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-5"
        tabIndex={0}
        aria-label={`${agent.display_name}'s workflow details`}
      >
        <p className="text-sm leading-6 text-gray-600">{agent.assignment}</p>

        <section className="mt-5">
          <h3 className="mb-2 text-xs font-medium text-muted-foreground">
            Research leads
          </h3>
          <ol className="space-y-1">
            {agent.leads.map((lead, index) => {
              const state = leadState(run, lead.label);
              return (
                <li
                  key={lead.label}
                  className={cn(
                    'flex items-center gap-2 border-l-2 py-1 pl-3 text-sm',
                    leadStyles[state],
                  )}
                >
                  <span className="w-3 text-xs text-gray-500">{index + 1}</span>
                  <span className="min-w-0 flex-1 truncate" title={lead.query}>
                    {lead.purpose}
                  </span>
                  <LeadMarker state={state} />
                </li>
              );
            })}
          </ol>
        </section>

        <section className="mt-5 border-t border-border pt-4">
          <h3 className="mb-3 flex items-center justify-between text-xs font-medium text-muted-foreground">
            Progress
            <span className="font-mono text-[11px] font-normal text-gray-500">
              {run?.progress ?? 0}%
            </span>
          </h3>
          <Progress
            value={run?.progress ?? 0}
            className="[&_[data-slot=progress-indicator]]:bg-primary [&_[data-slot=progress-track]]:bg-muted"
          />
          <div
            className={cn(
              'mt-4 grid gap-1',
              agent.filing_targets.length ? 'grid-cols-5' : 'grid-cols-4',
            )}
          >
            {workflowSteps.map(({ label, icon: Icon }, index) => {
              const active = running && stepIndexes[activeStep] === index;
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
                      ? 'text-tier-1-text'
                      : active
                        ? 'text-dodger-blue-600'
                        : 'text-gray-500',
                  )}
                >
                  <div
                    className={cn(
                      'grid size-8 place-items-center rounded-md border bg-muted',
                      complete
                        ? 'border-tier-1/50'
                        : active
                          ? 'border-dodger-blue-300'
                          : 'border-border',
                    )}
                  >
                    <Icon
                      className={cn(
                        'size-4',
                        active && running && 'motion-safe:animate-pulse',
                      )}
                    />
                  </div>
                  <span className="text-[11px]">{label}</span>
                </div>
              );
            })}
          </div>
        </section>

        <FilingAttempts agent={agent} run={run} />

        {run && run.events.length > 0 && <Timeline run={run} />}

        {run && terminalStatuses.has(run.status) && <FinalPanel run={run} />}
        {startError && (
          <p className="mt-3 text-xs leading-5 text-tier-4-text" role="alert">
            {startError}
          </p>
        )}
      </CardContent>

      <div className="shrink-0 border-t border-border px-5 py-4">
        <Button
          className="h-10 w-full"
          aria-label={`Start ${agent.display_name}'s workflow`}
          disabled={running}
          onClick={() => onStart(agent.slug)}
        >
          {awaitingApproval ? (
            <Clock data-icon="inline-start" />
          ) : running ? (
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

  const setStartError = useCallback(
    (agentSlug: AgentSlug, message: string | undefined) => {
      setStartErrors((current) => ({ ...current, [agentSlug]: message }));
    },
    [],
  );

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
        setStartError(
          agentSlug,
          'The live event stream disconnected. Retrying…',
        );
        return null;
      }
    },
    [mergeRun, setStartError],
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
        setStartError(agentSlug, undefined);
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
    [refreshFiledDocuments, refreshRun, setStartError],
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
    setStartError(agentSlug, undefined);
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
      setStartError(agentSlug, message);
      if ((error as { status?: number }).status !== 409) setApiState('offline');
    }
  }

  const idleAgents = agents.filter((agent) => {
    const run = runs[agent.slug];
    return !run || terminalStatuses.has(run.status);
  });

  function startAll() {
    for (const agent of idleAgents) void startWorkflow(agent.slug);
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
    <main className="min-h-screen bg-background text-gray-900">
      <header className="sticky top-0 z-20 flex h-16 items-center justify-between gap-4 border-b border-border bg-white/95 px-4 backdrop-blur sm:px-5 lg:px-7">
        <div className="flex min-w-0 items-center gap-3">
          <OpenBoxLogo className="h-8 shrink-0 text-gray-950" title="OpenBox" />
          <div className="min-w-0 border-l border-border pl-3">
            <h1 className="truncate text-sm font-semibold text-gray-950">
              Barrier Demo
            </h1>
            <p className="hidden truncate text-xs text-muted-foreground sm:block">
              Every read and filing is decided by OpenBox, not by this app
            </p>
          </div>
        </div>

        <output
          className={cn(
            'flex shrink-0 items-center gap-2 text-xs',
            connection.text,
          )}
        >
          <span className={cn('size-2 rounded-full', connection.color)} />
          <ConnectionIcon
            className={cn(
              'hidden size-3.5 sm:block',
              apiState === 'connecting' && 'animate-spin',
            )}
          />
          <span className="hidden sm:inline">{connection.label}</span>
          <span className="sm:hidden">
            {apiState === 'online' ? 'Live' : connection.label}
          </span>
        </output>
      </header>

      <div className="grid min-h-[calc(100vh-4rem)] grid-cols-1 lg:grid-cols-[300px_minmax(0,1fr)]">
        <DocumentTree
          library={library}
          filedLibrary={filedLibrary}
          activities={documentActivities}
          apiState={apiState}
        />

        <section className="min-w-0 px-4 py-6 sm:px-6 lg:px-8 lg:py-7">
          <div className="mx-auto max-w-[1480px]">
            {apiState === 'offline' && (
              <div
                className="mb-5 flex items-start gap-2 rounded-r-md border-l-2 border-tier-3 bg-tier-3-badge/50 px-3 py-2.5 text-sm leading-6 text-tier-3-text"
                role="alert"
              >
                <TriangleAlert className="mt-1 size-4 shrink-0" />
                <span>
                  Workflows need the local Python API. Run{' '}
                  <code className="font-mono">uv run barrier-web</code> from the
                  project folder, then reload this page.
                </span>
              </div>
            )}

            <div className="mb-4 flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
              <div>
                <h2 className="text-xl font-semibold tracking-tight text-gray-950">
                  Who can reach which client
                </h2>
                <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
                  Each cell is the decision OpenBox returned for that agent and
                  client folder. It fills in live as the agents run. Hover a
                  blocked cell for the reason.
                </p>
              </div>
              <Button
                className="h-10 shrink-0"
                disabled={idleAgents.length === 0 || apiState === 'offline'}
                onClick={startAll}
              >
                <Play data-icon="inline-start" className="fill-current" />
                {idleAgents.length === agents.length
                  ? 'Start all agents'
                  : idleAgents.length === 0
                    ? 'All agents running'
                    : `Start remaining ${idleAgents.length}`}
              </Button>
            </div>

            <OutcomeMatrix agents={agents} runs={runs} library={library} />

            <h2 className="mt-8 mb-4 text-base font-semibold text-gray-950">
              Agent workflows
            </h2>
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
