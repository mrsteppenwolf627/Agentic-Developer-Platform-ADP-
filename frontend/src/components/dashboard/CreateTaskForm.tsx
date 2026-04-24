import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTask } from '../../hooks/useTask';
import { taskSchema } from '../../utils/validators';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, X, Loader } from 'lucide-react';

export const CreateTaskForm = () => {
  const [isOpen, setIsOpen] = useState(false);
  const { createTask, isLoading } = useTask();
  
  const { register, handleSubmit, reset, formState: { errors } } = useForm({
    resolver: zodResolver(taskSchema),
  });

  const onSubmit = async (data: any) => {
    await createTask(data.title, data.description);
    reset();
    setIsOpen(false);
  };

  return (
    <>
      <div className="mb-6">
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={() => setIsOpen(true)}
          className="bg-[var(--accent)] text-white px-4 py-2 rounded-lg font-medium hover:bg-[var(--accent-hover)] transition-colors flex items-center gap-2"
        >
          <Plus size={18} />
          Nueva Tarea
        </motion.button>
      </div>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <motion.div
              className="bg-white rounded-xl p-6 w-full max-w-md shadow-2xl"
              initial={{ scale: 0.95, opacity: 0, y: 20 }}
              animate={{ scale: 1, opacity: 1, y: 0 }}
              exit={{ scale: 0.95, opacity: 0, y: 20 }}
            >
              <div className="flex justify-between items-center mb-6">
                <h2 className="text-xl font-semibold text-[var(--text-primary)]">Crear Tarea</h2>
                <button 
                  onClick={() => setIsOpen(false)}
                  className="text-[var(--text-tertiary)] hover:text-[var(--text-primary)] transition-colors"
                >
                  <X size={24} />
                </button>
              </div>

              <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-[var(--text-primary)] mb-1">
                    Título
                  </label>
                  <input
                    type="text"
                    {...register('title')}
                    className="w-full px-3 py-2 border border-[var(--border)] rounded-lg text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent)] transition-colors"
                    placeholder="Ej: Implementar login"
                  />
                  {errors.title && (
                    <p className="text-[var(--error)] text-sm mt-1">{errors.title.message?.toString()}</p>
                  )}
                </div>

                <div>
                  <label className="block text-sm font-medium text-[var(--text-primary)] mb-1">
                    Descripción
                  </label>
                  <textarea
                    {...register('description')}
                    rows={4}
                    className="w-full px-3 py-2 border border-[var(--border)] rounded-lg text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent)] transition-colors resize-none"
                    placeholder="Detalles de la tarea..."
                  />
                  {errors.description && (
                    <p className="text-[var(--error)] text-sm mt-1">{errors.description.message?.toString()}</p>
                  )}
                </div>

                <div className="flex justify-end gap-3 pt-4">
                  <button
                    type="button"
                    onClick={() => setIsOpen(false)}
                    className="px-4 py-2 text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)] rounded-lg transition-colors font-medium"
                  >
                    Cancelar
                  </button>
                  <motion.button
                    type="submit"
                    disabled={isLoading}
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    className="bg-[var(--accent)] text-white px-4 py-2 rounded-lg font-medium hover:bg-[var(--accent-hover)] disabled:opacity-50 transition-colors flex items-center gap-2"
                  >
                    {isLoading ? <Loader size={18} className="animate-spin" /> : 'Crear'}
                  </motion.button>
                </div>
              </form>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
};