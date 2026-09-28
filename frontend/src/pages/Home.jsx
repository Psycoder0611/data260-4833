import { useEffect, useState } from "react";
import axios from "axios";

function Home() {
  const [records, setRecords] = useState([]);
  const [isAuthenticated, setIsAuthenticated] = useState(null);

  useEffect(() => {
    const loadData = async () => {
      try {
        await axios.get(
          "http://localhost:8333/api/me",
          {
            withCredentials: true,
          }
        );

        setIsAuthenticated(true);

        const response = await axios.get(
          "http://localhost:8333/api/hw4/trials",
          {
            withCredentials: true,
          }
        );

        setRecords(response.data);
      } catch (error) {
        setIsAuthenticated(false);
      }
    };

    loadData();
  }, []);

  if (isAuthenticated === null) {
    return <p>Loading...</p>;
  }

  if (!isAuthenticated) {
    return (
      <div className="page-container">
        <h1>Clinical Trial Listings</h1>
        <p>Login required</p>
      </div>
    );
  }

  return (
    <div className="page-container">
      <h1>Clinical Trial Listings</h1>

      {records.length === 0 ? (
        <p>No clinical trials found.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Trial Title</th>
              <th>Sponsor</th>
            </tr>
          </thead>

          <tbody>
            {records.map((record) => (
              <tr key={record.id}>
                <td>{record.id}</td>
                <td>{record.trialTitle}</td>
                <td>{record.sponsor}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default Home;