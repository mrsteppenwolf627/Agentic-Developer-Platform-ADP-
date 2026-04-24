export interface Task {
  id: string;
  title: string;
  description: string;
  status: 'pending' | 'in_progress' | 'completed';
  assigned_model: string; // Gemini, Claude, Codex
  created_at: string;
  completed_at?: string;
}

export interface CreateTaskRequest {
  title: string;
  description: string;
}

export interface TaskStats {
  total: number;
  completed: number;
  pending: number;
}