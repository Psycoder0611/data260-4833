import { useEffect } from "react";
import { useDispatch, useSelector } from "react-redux";

import { fetchTrials } from "../features/trials/trialsSlice";


function Home() {
  const dispatch = useDispatch();

  const {
    records,
    loading,
    error
  } = useSelector((state) => state.trials);


  useEffect(() => {
    dispatch(fetchTrials());
  }, [dispatch]);


  if (loading) {
    return (
      <div className="page-container">
        <h1>Clinical Trial Listings</h1>
        <p>Loading clinical trials...</p>
      </div>
    );
  }


  return (
    <div className="page-container">
      <h1>Clinical Trial Listings</h1>

      {error && (
        <p>{error}</p>
      )}

      {records.length === 0 ? (
        <p>No clinical trials found.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Trial Title</th>
              <th>Trial Code</th>
              <th>Participant Capacity</th>
              <th>Organization ID</th>
            </tr>
          </thead>

          <tbody>
            {records.map((record) => (
              <tr key={record.id}>
                <td>{record.id}</td>
                <td>{record.trialTitle}</td>
                <td>{record.trial_code}</td>
                <td>{record.participant_capacity}</td>
                <td>{record.organization_id}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}


export default Home;