import { z } from 'zod'
export const EventSchema = z.object({
  type: z.literal('monitor_event'), event: z.string(), message: z.string(),
  run_id: z.string(), sequence: z.number(), timestamp: z.string(),
  data: z.record(z.unknown()),
})
export type RunEvent = z.infer<typeof EventSchema>
export const TaskSchema = z.object({
  run_id: z.string(), thread_id: z.string(),
  status: z.enum(['queued', 'running', 'succeeded', 'failed', 'interrupted']),
  result: z.string().nullable(), error: z.string().nullable(),
  events: z.array(EventSchema), truncated: z.boolean(),
})
export type TaskSnapshot = z.infer<typeof TaskSchema>
export const HealthSchema = z.object({
  status: z.literal('ok'), instance_id: z.string(),
  capabilities: z.object({ search: z.boolean(), database: z.boolean(), knowledge: z.boolean() }),
})
export type Health = z.infer<typeof HealthSchema>
export const FileSchema = z.object({
  uuid: z.string(), originalName: z.string(), workspaceName: z.string(),
  contentType: z.string(), sizeBytes: z.number(), createdAt: z.string(),
  source: z.enum(['uploaded', 'generated']),
})
export type SessionFile = z.infer<typeof FileSchema>
export const MessageSchema = z.object({
  uuid: z.string(), role: z.enum(['user', 'assistant']), content: z.string(),
  runId: z.string().optional(), error: z.boolean().optional(),
})
export const SessionSchema = z.object({
  uuid: z.string(), title: z.string(), instanceId: z.string(), createdAt: z.number(),
  messages: z.array(MessageSchema), runId: z.string().optional(),
  status: z.enum(['idle','queued','running','succeeded','failed','interrupted']),
  events: z.array(EventSchema), truncated: z.boolean().default(false),
})
export type Session = z.infer<typeof SessionSchema>
