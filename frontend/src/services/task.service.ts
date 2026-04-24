import api from './api';
import { Task, CreateTaskRequest } from '../types/task';

export const taskService = {
  async getTasks(): Promise<Task[]> {
    const { data } = await api.get('/api/tasks');
    return data;
  },

  async getTask(id: string): Promise<Task> {
    const { data } = await api.get(`/api/tasks/${id}`);
    return data;
  },

  async createTask(payload: CreateTaskRequest): Promise<Task> {
    const { data } = await api.post('/api/tasks', payload);
    return data;
  },

  async updateTask(id: string, payload: Partial<Task>): Promise<Task> {
    const { data } = await api.put(`/api/tasks/${id}`, payload);
    return data;
  },

  async deleteTask(id: string): Promise<void> {
    await api.delete(`/api/tasks/${id}`);
  },

  async getStats() {
    const { data } = await api.get('/api/tasks/stats');
    return data;
  },
};