import { useEffect } from 'react';
import { Header } from '../components/common/Header';
import { TaskTable } from '../components/dashboard/TaskTable';
import { CreateTaskForm } from '../components/dashboard/CreateTaskForm';
import { TaskStats } from '../components/dashboard/TaskStats';
import { UserProfile } from '../components/dashboard/UserProfile';
import { useAuthStore } from '../store/authStore';
import { motion } from 'framer-motion';

export const Dashboard = () => {
  const { user } = useAuthStore();

  return (
    <div className="min-h-screen bg-[var(--bg-secondary)]">
      <Header />
      
      <main className="max-w-7xl mx-auto px-4 py-8">
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <div className="flex flex-col md:flex-row gap-6">
            <div className="w-full md:w-1/4">
              <UserProfile />
              <div className="bg-white p-4 rounded-xl border border-[var(--border)] shadow-[var(--shadow-light)]">
                <h3 className="font-medium text-[var(--text-primary)] mb-2">Info</h3>
                <p className="text-sm text-[var(--text-secondary)]">
                  Aquí puedes administrar tus tareas y monitorear el progreso de los modelos de IA asignados.
                </p>
              </div>
            </div>
            
            <div className="w-full md:w-3/4">
              <h2 className="text-2xl font-semibold text-[var(--text-primary)] mb-6">
                Panel de Control
              </h2>
              
              <TaskStats />
              
              <div className="bg-white p-6 rounded-xl border border-[var(--border)] shadow-[var(--shadow-light)]">
                <div className="flex justify-between items-center mb-6">
                  <h3 className="text-lg font-semibold text-[var(--text-primary)]">Tus Tareas</h3>
                  <CreateTaskForm />
                </div>
                <TaskTable />
              </div>
            </div>
          </div>
        </motion.div>
      </main>
    </div>
  );
};