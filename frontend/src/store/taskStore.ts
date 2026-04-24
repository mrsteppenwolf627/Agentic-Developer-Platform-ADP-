import { create } from 'zustand';
import { Task, TaskStats } from '../types/task';

interface TaskStore {
  tasks: Task[];
  stats: TaskStats;
  isLoading: boolean;

  setTasks: (tasks: Task[]) => void;
  setStats: (stats: TaskStats) => void;
  setIsLoading: (loading: boolean) => void;
  addTask: (task: Task) => void;
  updateTask: (id: string, task: Partial<Task>) => void;
}

export const useTaskStore = create<TaskStore>((set) => ({
  tasks: [],
  stats: { total: 0, completed: 0, pending: 0 },
  isLoading: false,

  setTasks: (tasks) => set({ tasks }),
  setStats: (stats) => set({ stats }),
  setIsLoading: (loading) => set({ isLoading: loading }),
  
  addTask: (task) => set((state) => ({
    tasks: [task, ...state.tasks],
  })),
  
  updateTask: (id, updates) => set((state) => ({
    tasks: state.tasks.map((t) => (t.id === id ? { ...t, ...updates } : t)),
  })),
}));