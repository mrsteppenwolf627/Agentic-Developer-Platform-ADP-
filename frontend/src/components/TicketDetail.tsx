import React, { useEffect, useState, useCallback } from 'react';
import { api, Ticket, Task } from '../api/client';
import { TaskCard } from './TaskCard';

interface Props {
  ticketId: string;
}

export const TicketDetail: React.FC<Props> = ({ ticketId }) => {
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [ticketData, tasksData] = await Promise.all([
        api.getTicket(ticketId),
        api.getTicketTasks(ticketId)
      ]);
      setTicket(ticketData);
      setTasks(tasksData);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [ticketId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  if (loading) return <div className="p-8 text-gray-500 flex justify-center items-center h-full">Loading details...</div>;
  if (!ticket) return <div className="p-8 text-red-500 flex justify-center items-center h-full">Ticket not found</div>;

  return (
    <div className="p-8 max-w-4xl mx-auto bg-white min-h-full">
      <div className="mb-8 border-b border-gray-200 pb-6">
        <div className="flex items-center gap-3 mb-2">
          <h1 className="text-3xl font-bold text-gray-900">{ticket.title}</h1>
          <span className="px-3 py-1 bg-gray-100 rounded-full text-sm font-medium border text-gray-700">{ticket.status}</span>
        </div>
        <p className="text-sm font-mono text-gray-500 mb-4">ID: {ticket.id}</p>
        <p className="text-gray-700 leading-relaxed">{ticket.description || 'No description provided.'}</p>
      </div>

      <h2 className="text-2xl font-bold mb-6 text-gray-800">Associated Tasks</h2>
      {tasks.length === 0 ? (
        <div className="text-center p-8 bg-gray-50 rounded-lg border border-dashed border-gray-300">
          <p className="text-gray-500">No tasks associated with this ticket yet.</p>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {tasks.map(task => (
            <TaskCard key={task.id} task={task} onUpdate={loadData} />
          ))}
        </div>
      )}
    </div>
  );
};
