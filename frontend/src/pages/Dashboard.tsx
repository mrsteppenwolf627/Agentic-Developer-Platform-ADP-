import React, { useState } from 'react';
import { TicketList } from '../components/TicketList';
import { TicketDetail } from '../components/TicketDetail';

export const Dashboard: React.FC = () => {
  const [selectedTicketId, setSelectedTicketId] = useState<string | null>(null);

  return (
    <div className="flex h-full bg-gray-50">
      <div className="w-1/3 min-w-[320px] max-w-sm border-r border-gray-200 bg-white overflow-y-auto shadow-sm z-10">
        <TicketList onSelect={setSelectedTicketId} selectedId={selectedTicketId} />
      </div>
      <div className="flex-1 overflow-y-auto">
        {selectedTicketId ? (
          <TicketDetail ticketId={selectedTicketId} />
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-gray-400 p-8 text-center">
            <svg className="w-16 h-16 text-gray-300 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
            <p className="text-xl font-medium text-gray-500">Select a ticket</p>
            <p className="mt-2 text-sm">Choose a ticket from the sidebar to view its details and tasks.</p>
          </div>
        )}
      </div>
    </div>
  );
};
