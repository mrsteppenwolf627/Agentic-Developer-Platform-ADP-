import { useTaskStore } from '../store/taskStore';
import { taskService } from '../services/task.service';
import { toast } from 'sonner';

export const useTask = () => {
  const { tasks, stats, setTasks, setStats, setIsLoading, isLoading } = useTaskStore();

  const loadTasks = async () => {
    setIsLoading(true);
    try {
      const data = await taskService.getTasks();
      setTasks(data);
      
      // Calcular stats
      const completed = data.filter((t) => t.status === 'completed').length;
      const pending = data.filter((t) => t.status === 'pending').length;
      setStats({
        total: data.length,
        completed,
        pending,
      });
    } catch (err) {
      toast.error('Error al cargar tareas');
    } finally {
      setIsLoading(false);
    }
  };

  const createTask = async (title: string, description: string) => {
    try {
      const task = await taskService.createTask({ title, description });
      toast.success('Tarea creada');
      await loadTasks();
      return task;
    } catch (err) {
      toast.error('Error al crear tarea');
    }
  };

  const updateTask = async (id: string, updates: any) => {
    try {
      await taskService.updateTask(id, updates);
      toast.success('Tarea actualizada');
      await loadTasks();
    } catch (err) {
      toast.error('Error al actualizar tarea');
    }
  };

  const deleteTask = async (id: string) => {
    try {
      await taskService.deleteTask(id);
      toast.success('Tarea eliminada');
      await loadTasks();
    } catch (err) {
      toast.error('Error al eliminar tarea');
    }
  };

  return {
    tasks,
    stats,
    isLoading,
    loadTasks,
    createTask,
    updateTask,
    deleteTask,
  };
};