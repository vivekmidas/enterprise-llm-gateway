/**
 * ===============================================================================
 * BLOCK COMMENT: ENTERPRISE GATEWAY CLIENT SDK (EPIC-ARCH-001)
 * Module: packages/gateway-client-ts/src/index.ts
 * Description:
 *     Lightweight, domain-agnostic client SDK for decoupled domain plants
 *     (e.g., Legal Plant, Knowledge/Education Plant).
 *     Provides typed methods to trigger and observe workflows on the Gateway.
 * ===============================================================================
 */

export interface GatewayClientConfig {
  baseUrl: string;
  authToken?: string;
  defaultHeaders?: Record<string, string>;
}

export interface WorkflowExecutionOptions {
  executionMode?: 'sync' | 'async';
  traceId?: string;
  metadata?: Record<string, any>;
}

export interface WorkflowExecutionResponse<T = any> {
  status: 'completed' | 'accepted' | 'failure' | string;
  workflow_id: string;
  trace_id: string;
  latency_ms?: number;
  result?: T;
  violations?: any[];
  error_message?: string;
}

export interface WorkflowTraceData {
  trace_id: string;
  workflow_id: string;
  status: string;
  latency_ms?: number;
  final_response?: any;
  agents_executed?: any[];
  violations?: any[];
  timestamp?: number;
}

export class GatewayClient {
  private baseUrl: string;
  private authToken?: string;
  private defaultHeaders: Record<string, string>;

  constructor(config: GatewayClientConfig) {
    this.baseUrl = config.baseUrl.replace(/\/+$/, '');
    this.authToken = config.authToken;
    this.defaultHeaders = config.defaultHeaders || {};
  }

  public setAuthToken(token: string): void {
    this.authToken = token;
  }

  private getHeaders(extra?: Record<string, string>): Record<string, string> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...this.defaultHeaders,
      ...extra,
    };
    if (this.authToken) {
      headers['Authorization'] = `Bearer ${this.authToken}`;
    }
    return headers;
  }

  /**
   * Executes a workflow by its unique ID or human-readable slug.
   * Supports both synchronous waiting and asynchronous background triggering.
   */
  public async executeWorkflow<T = any>(
    workflowIdOrSlug: string,
    inputData: any,
    options?: WorkflowExecutionOptions
  ): Promise<WorkflowExecutionResponse<T>> {
    const url = `${this.baseUrl}/workflows/${encodeURIComponent(workflowIdOrSlug)}/execute`;
    const body = {
      input_data: inputData,
      execution_mode: options?.executionMode || 'sync',
      trace_id: options?.traceId,
      metadata: options?.metadata || {},
    };

    const res = await fetch(url, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`Gateway workflow execution failed (${res.status}): ${errText}`);
    }

    return res.json();
  }

  /**
   * Retrieves workflow execution trace state and observability telemetry.
   */
  public async getTrace(traceId: string): Promise<WorkflowTraceData> {
    const url = `${this.baseUrl}/workflows/traces/${encodeURIComponent(traceId)}`;
    const res = await fetch(url, {
      method: 'GET',
      headers: this.getHeaders(),
    });

    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`Gateway trace lookup failed (${res.status}): ${errText}`);
    }

    return res.json();
  }

  /**
   * Polls an asynchronous workflow trace until completion or timeout.
   */
  public async pollTrace(
    traceId: string,
    intervalMs: number = 1000,
    maxAttempts: number = 30
  ): Promise<WorkflowTraceData> {
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      const trace = await this.getTrace(traceId);
      if (trace.status === 'completed' || trace.status === 'failure' || trace.status === 'stopped') {
        return trace;
      }
      await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }
    throw new Error(`Polling timed out for trace '${traceId}' after ${maxAttempts} attempts`);
  }
}

