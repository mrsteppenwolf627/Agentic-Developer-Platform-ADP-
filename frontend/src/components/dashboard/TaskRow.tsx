import { Task } from '../../types/task';
import { useTask } from '../../hooks/useTask';
import { motion } from 'framer-motion';
import { Trash2, CheckCircle } from 'lucide-react';

export const TaskRow = ({ task }: { task: Task }) => {
  const { updateTask, deleteTask } = useTask();

  const modelColors: Record<string, string> = {
    'gemini-2.0-flash': 'bg-blue-100 text-blue-700',
    'claude-opus': 'bg-purple-100 text-purple-700',
    'gpt-4o': 'bg-green-100 text-green-700',
  };

  return (
    <motion.tr
      className="border-b border-[var(--border-light)] hover:bg-[var(--bg-secondary)] transition-colors"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
    >
      <td className="py-3 px-4 text-[var(--text-primary)] text-sm">{task.title}</td>
      <td className="py-3 px-4">
        <span className={`px-2 py-1 rounded text-xs font-medium ${
          task.status === 'completed' ? 'bg-[var(--success-light)] text-[var(--success)]' :
          task.status === 'in_progress' ? 'bg-[var(--warning-light)] text-[var(--warning)]' :
          'bg-[var(--bg-tertiary)] text-[var(--text-secondary)]'
        }`}>
          {task.status}
        </span>
      </td>
      <td className="py-3 px-4">
        <span className={`px-2 py-1 rounded text-xs font-medium ${modelColors[task.assigned_model] || 'bg-gray-100 text-gray-700'}`}>
          {task.assigned_model || 'Desconocido'}
        </span>
      </td>
      <td className="py-3 px-4 flex gap-2">
        {task.status !== 'completed' && (
          <motion.button
            whileHover={{ scale: 1.1 }}
            onClick={() => updateTask(task.id, { status: 'completed' })}
            className="p-1 text-[var(--success)] hover:bg-[var(--success-light)] rounded transition-colors"
            title="Marcar como completada"
          >
            <CheckCircle size={18} />
          </motion.button>
        )}
        <motion.button
          whileHover={{ scale: 1.1 }}
          onClick={() => deleteTask(task.id)}
          className="p-1 text-[var(--error)] hover:bg-[var(--error-light)] rounded transition-colors"
            title="Eliminar tarea"
        >
          <Trash2 size={18} />
        </motion.button>
      </td>
    </motion.tr>
  );
};