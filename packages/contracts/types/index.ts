/** 前后端共享类型定义 — 接口契约的单一事实来源 */

// === Enums ===
export type ActionType = 'CONFIRMED' | 'REJECTED';
export type AuditStatus = 'PENDING' | 'SUSPECTED' | 'VERIFIED' | 'CLEAN';
export type ProcessStatus = 'UNPROCESSED' | 'CONFIRMED' | 'REJECTED';
export type FraudType = 'PASSENGER_USES_TRUCK_OBU_NON_NEW_A' | 'ENTRY_EXIT_MISMATCH';

// === Request DTOs ===
export interface AggregateRequest {
  days?: number;
  limit?: number;
}

export interface ProcessRequest {
  action: ActionType;
  operator?: string;
  comments?: string;
}

export interface DetectRequest {
  passid: string;
}

// === Response DTOs ===
export interface TripResponse {
  id: number;
  passid: string;
  entry_time?: string;
  entry_station_name?: string;
  entry_lane_id?: string;
  entry_vehicle_id?: string;
  entry_vehicle_type?: number;
  entry_vehicle_color?: number;
  entry_obu_id?: string;
  entry_media_type?: number;
  entry_image_license?: string;
  entry_image_trans?: string;
  exit_time?: string;
  exit_station_name?: string;
  exit_lane_id?: string;
  exit_vehicle_id?: string;
  exit_vehicle_type?: number;
  exit_vehicle_color?: number;
  exit_obu_id?: string;
  exit_media_type?: number;
  exit_image_license?: string;
  exit_image_trans?: string;
  gantry_count: number;
  audit_status: string;
  risk_score: number;
  entry_visual_type?: string;
  exit_visual_type?: string;
  fingerprint_sim?: number;
}

export interface TripListResponse {
  trips: TripResponse[];
  total: number;
  limit: number;
  offset: number;
}

export interface TripDetailResponse extends TripResponse {
  /** 门架抓拍图片流水（JSON 字符串） */
  gantry_image_records?: string;
  /** 该行程触发的所有稽核结果（可空） */
  audit_results: SuspectResponse[];
}

export interface SuspectResponse {
  id: number;
  audit_trip_id: number;
  fraud_type: string;
  passid: string;
  entry_time?: string;
  exit_time?: string;
  entry_station_name?: string;
  exit_station_name?: string;
  entry_lane_id?: string;
  exit_lane_id?: string;
  entry_vehicle_id?: string;
  exit_vehicle_id?: string;
  entry_vehicle_type?: number;
  exit_vehicle_type?: number;
  entry_vehicle_color?: number;
  exit_vehicle_color?: number;
  entry_obu_id?: string;
  exit_obu_id?: string;
  entry_media_type?: number;
  exit_media_type?: number;
  entry_image_license?: string;
  entry_image_trans?: string;
  exit_image_license?: string;
  exit_image_trans?: string;
  entry_visual_type?: string;
  exit_visual_type?: string;
  entry_color?: string;
  exit_color?: string;
  is_suspicious: number;
  risk_score: number;
  process_status: string;
  details?: string;
  gantry_count: number;
  gantry_records?: string;
  gantry_image_records?: string;
  // LLM 二次判定结果（由 llm_batch.py 写入；未判定时为 undefined）
  llm_is_same_vehicle?: number;
  llm_confidence?: number;
  llm_reason?: string;
  llm_model?: string;
  llm_checked_at?: string;
}

export interface SuspectListResponse {
  suspects: SuspectResponse[];
  total: number;
}

export interface StatsResponse {
  total_trips: number;
  verified_trips: number;
  suspected_trips: number;
  confirmed_fraud: number;
}

export interface AggregationStatus {
  status: 'running' | 'completed' | 'error' | 'stopped' | 'not_found';
  current?: number;
  total?: number;
  count?: number;
  passid?: string;
  message?: string;
}

// === 车辆查询（原始 Doris 数据） ===

/** 来自 Doris 原始表的行程聚合结果（不含检测后字段） */
export interface RawTripResponse {
  passid: string;
  entry_time?: string;
  entry_station_name?: string;
  entry_vehicle_id?: string;
  entry_vehicle_color?: string;
  entry_vehicle_type?: number;
  entry_obu_id?: string;
  exit_time?: string;
  exit_station_name?: string;
  exit_vehicle_id?: string;
  exit_vehicle_color?: string;
  exit_vehicle_type?: number;
  exit_obu_id?: string;
  gantry_count: number;
}

export interface RawTripListResponse {
  trips: RawTripResponse[];
  total: number;
  limit: number;
  offset: number;
}

/** 原始数据视角下的行程详情（无 audit_results） */
export interface RawTripDetailResponse extends RawTripResponse {
  entry_lane_id?: string;
  exit_lane_id?: string;
  entry_image_license?: string;
  entry_image_trans?: string;
  exit_image_license?: string;
  exit_image_trans?: string;
  gantry_records?: string;
  gantry_image_records?: string;
}

// === MaaS 出入口车辆双图比对 ===

/** 手动触发 MaaS 双图比对的请求体（车牌特写 image_license） */
export interface DetectEntryExitLLMRequest {
  passid: string;
}

/** MaaS 双图比对响应。结构化 JSON 由 LLM 输出，前端可渲染置信度与依据。 */
export interface LlmVehicleCompareResponse {
  passid: string;
  is_same_vehicle: boolean;
  confidence: number;
  reason: string;
  entry_image_url?: string;
  exit_image_url?: string;
  model: string;
  elapsed_ms: number;
}
