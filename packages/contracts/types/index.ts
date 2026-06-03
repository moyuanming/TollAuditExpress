/** 前后端共享类型定义 — 接口契约的单一事实来源 */

// === Enums ===
export type ActionType = 'CONFIRMED' | 'REJECTED';
export type AuditStatus = 'PENDING' | 'SUSPECTED' | 'VERIFIED' | 'CLEAN';
export type ProcessStatus = 'UNPROCESSED' | 'CONFIRMED' | 'REJECTED';
export type FraudType = 'TRUCK_USES_PASSENGER_OBU' | 'ENTRY_EXIT_MISMATCH';

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

export interface SuspectResponse {
  id: number;
  audit_trip_id: number;
  fraud_type: string;
  passid: string;
  entry_time?: string;
  exit_time?: string;
  entry_vehicle_id?: string;
  exit_vehicle_id?: string;
  entry_vehicle_type?: number;
  exit_vehicle_type?: number;
  entry_visual_type?: string;
  exit_visual_type?: string;
  is_suspicious: number;
  risk_score: number;
  process_status: string;
  details?: string;
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
