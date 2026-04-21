const BASE_URL = 'https://agentic-developer-platform-adp.vercel.app';

export interface Ticket {
  id: string;
  title: string;
  status: string;
  priority: string;
  description?: string;
}

export interface Task {
  id: string;
  ticket_id: string;
  name: string;
  assigned_model: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  evaluation_score?: number;
  evaluation_findings?: string;
  error_message?: string;
}

export const api = {
  getTickets: async (): Promise<Ticket[]> => {
    const res = await fetch(`${BASE_URL}/api/tickets`);
    if (!res.ok) throw new Error('Failed to fetch tickets');
    return res.json();
  },
  getTicket: async (id: string): Promise<Ticket> => {
    const res = await fetch(`${BASE_URL}/api/tickets/${id}`);
    if (!res.ok) throw new Error('Failed to fetch ticket');
    return res.json();
  },
  getTicketTasks: async (ticketId: string): Promise<Task[]> => {
    const res = await fetch(`${BASE_URL}/api/tickets/${ticketId}/tasks`);
    if (!res.ok) throw new Error('Failed to fetch tasks');
    return res.json();
  },
  executeTask: async (id: string): Promise<any> => {
    const res = await fetch(`${BASE_URL}/api/tasks/${id}/execute`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to execute task');
    return res.json();
  },
  rollbackTask: async (id: string): Promise<any> => {
    const res = await fetch(`${BASE_URL}/api/tasks/${id}/rollback`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to rollback task');
    return res.json();
  }
};
