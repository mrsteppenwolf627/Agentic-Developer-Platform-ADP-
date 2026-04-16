import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { TicketList } from '../components/TicketList';

describe('TicketList', () => {
  beforeEach(() => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => [
        { id: 'ticket-1', title: 'Fix auth flow', status: 'pending', priority: 'P0' },
        { id: 'ticket-2', title: 'Add CI pipeline', status: 'in_progress', priority: 'P1' },
        { id: 'ticket-3', title: 'Ship dashboard', status: 'completed', priority: 'P2' }
      ]
    }) as jest.Mock;
  });

  afterEach(() => {
    jest.resetAllMocks();
  });

  it('renders fetched tickets and selects one on click', async () => {
    const onSelect = jest.fn();
    render(<TicketList onSelect={onSelect} selectedId={null} />);

    await waitFor(() => {
      expect(screen.getByText('Fix auth flow')).toBeInTheDocument();
      expect(screen.getByText('Add CI pipeline')).toBeInTheDocument();
      expect(screen.getByText('Ship dashboard')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByText('Add CI pipeline'));

    expect(onSelect).toHaveBeenCalledWith('ticket-2');
  });
});

