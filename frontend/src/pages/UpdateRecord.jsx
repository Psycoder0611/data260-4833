import { useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";

function UpdateRecord({ apiBaseUrl }) {
  const [id, setId] = useState("");
  const [trialTitle, setTrialTitle] = useState("");
  const [sponsor, setSponsor] = useState("");
  const [error, setError] = useState("");

  const navigate = useNavigate();

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError("");

    try {
      await axios.put(
        `${apiBaseUrl}/api/hw4/trials/${id}`,
        {
          trialTitle: trialTitle.trim(),
          sponsor: sponsor.trim(),
        },
        {
          withCredentials: true,
        }
      );

      navigate("/");
    } catch (err) {
      if (err.response?.status === 401) {
        setError("Login required");
      } else if (err.response?.status === 404) {
        setError("Clinical trial not found");
      } else {
        setError("Unable to update clinical trial");
      }
    }
  };

  return (
    <div className="page-container">
      <h1>Update Clinical Trial</h1>

      <form onSubmit={handleSubmit}>
        <div>
          <label htmlFor="id">Trial ID</label>
          <br />

          <input
            id="id"
            type="number"
            value={id}
            onChange={(event) => setId(event.target.value)}
            placeholder="Enter trial ID"
            required
          />
        </div>

        <div>
          <label htmlFor="trialTitle">Trial Title</label>
          <br />

          <input
            id="trialTitle"
            type="text"
            value={trialTitle}
            onChange={(event) => setTrialTitle(event.target.value)}
            placeholder="Enter updated trial title"
            required
          />
        </div>

        <div>
          <label htmlFor="sponsor">Sponsor</label>
          <br />

          <input
            id="sponsor"
            type="text"
            value={sponsor}
            onChange={(event) => setSponsor(event.target.value)}
            placeholder="Enter updated sponsor"
            required
          />
        </div>

        <button type="submit">Update Clinical Trial</button>
      </form>

      {error && <p>{error}</p>}
    </div>
  );
}

export default UpdateRecord;