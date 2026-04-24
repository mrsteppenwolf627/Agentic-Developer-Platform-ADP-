import { useTask } from '../../hooks/useTask';
import { motion } from 'framer-motion';

export const TaskStats = () => {
  const { stats } = useTask();

  return (
    <div className="grid grid-cols-3 gap-4 mb-8">
      <motion.div 
        className="bg-white p-4 rounded-xl border border-[var(--border)] shadow-[var(--shadow-light)]"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
      >
        <div className="text-sm text-[var(--text-secondary)] font-medium mb-1">Total</div>
        <div className="text-3xl font-bold text-[var(--text-primary)]">{stats.total}</div>
      </motion.div>
      
      <motion.div 
        className="bg-white p-4 rounded-xl border border-[var(--border)] shadow-[var(--shadow-light)]"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
      >
        <div className="text-sm text-[var(--text-secondary)] font-medium mb-1">Completadas</div>
        <div className="text-3xl font-bold text-[var(--success)]">{stats.completed}</div>
      </motion.div>
      
      <motion.div 
        className="bg-white p-4 rounded-xl border border-[var(--border)] shadow-[var(--shadow-light)]"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
      >
        <div className="text-sm text-[var(--text-secondary)] font-medium mb-1">Pendientes</div>
        <div className="text-3xl font-bold text-[var(--warning)]">{stats.pending}</div>
      </motion.div>
    </div>
  );
};