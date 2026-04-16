import React, { useEffect, useState } from 'react';
import { api, Ticket } from '../api/client';

interface Props {
  onSelect: (id: string) => void;
  selectedId?: string | null;
}

export const TicketList: React.FC<Props> = ({ onSelect, selectedId }) => {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getTickets().then(data => {
      setTickets(data);
      setLoading(false);
    }).catch(err => {
      console.error(err);
      setLoading(false);
    });
  }, []);

  if (loading) return <div className="p-4 text-gray-500">Loading tickets...</div>;

  return (
    <div className="flex flex-col gap-3 p-4">
      <h2 className="font-bold text-xl mb-2 text-gray-800 px-2">Active Tickets</h2>
      {tickets.map(ticket => (
        <div 
          key={ticket.id} 
          onClick={() => onSelect(ticket.id)}
          className={`p-4 border rounded-lg cursor-pointer transition-all ${
            selectedId === ticket.id 
              ? 'border-indigo-500 bg-indigo-50 shadow-sm' 
              : 'border-gray-200 hover:border-indigo-300 hover:bg-gray-50'
          }`}
        >
          <div className="flex justify-between items-center mb-2">
            <span className="font-mono font-semibold text-xs text-gray-500">#{ticket.id.slice(0, 8)}</span>
            <span className={`text-xs px-2 py-1 rounded-full font-medium ${
              ticket.priority.toLowerCase() === 'high' ? 'bg-red-100 text-red-700' :
              ticket.priority.toLowerCase() === 'medium' ? 'bg-yellow-100 text-yellow-700' :
              'bg-blue-100 text-blue-700'
            }`}>
              {ticket.priority}
            </span>
          </div>
          <h3 className="font-semibold text-gray-900 leading-snug">{ticket.title}</h3>
          <div className="text-sm font-medium text-gray-500 mt-3 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-gray-400"></span>
            {ticket.status}
          </div>
        </div>
      ))}
      {tickets.length === 0 && (
        <div className="text-center p-6 border border-dashed rounded-lg bg-gray-50">
          <p className="text-gray-500">No tickets found in the queue.</p>
        </div>
      )}
    </div>
  );
};
