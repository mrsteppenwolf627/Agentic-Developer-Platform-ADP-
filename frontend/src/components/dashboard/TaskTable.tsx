import { useTask } from '../../hooks/useTask';
import { useEffect } from 'react';
import { TaskRow } from './TaskRow';
import { Loader } from 'lucide-react';

export const TaskTable = () => {
  const { tasks, isLoading, loadTasks } = useTask();

  useEffect(() => {
    loadTasks();
  }, []);

  if (isLoading) {
    return (
      <div className="flex justify-center py-8">
        <Loader className="animate-spin text-[var(--accent)]" />
      </div>
    );
  }

  return (
    <div className="overflow-x-auto bg-white rounded-lg border border-[var(--border)] shadow-[var(--shadow-light)]">
      <table className="w-full border-collapse">
        <thead className="bg-[var(--bg-secondary)] border-b border-[var(--border)]">
          <tr>
            <th className="text-left py-3 px-4 font-semibold text-[var(--text-primary)] text-sm">Título</th>
            <th className="text-left py-3 px-4 font-semibold text-[var(--text-primary)] text-sm">Estado</th>
            <th className="text-left py-3 px-4 font-semibold text-[var(--text-primary)] text-sm">Modelo IA</th>
            <th className="text-left py-3 px-4 font-semibold text-[var(--text-primary)] text-sm">Acciones</th>
          </tr>
        </thead>
        <tbody>
          {tasks.map((task) => (
            <TaskRow key={task.id} task={task} />
          ))}
        </tbody>
      </table>
      
      {tasks.length === 0 && (
        <div className="text-center py-8 text-[var(--text-secondary)]">
          No hay tareas aún. Crea una para empezar.
        </div>
      )}
    </div>
  );
};