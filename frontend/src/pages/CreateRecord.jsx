import { useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";

function CreateRecord({ apiBaseUrl }) {
  const [trialTitle, setTrialTitle] = useState("");
  const [sponsor, setSponsor] = useState("");
  const [error, setError] = useState("");

  const navigate = useNavigate();

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError("");

    try {
      await axios.post(
        `${apiBaseUrl}/api/hw4/trials`,
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
      } else {
        setError("Unable to create clinical trial");
      }
    }
  };

  return (
    <div className="page-container">
      <h1>Add Clinical Trial</h1>

      <form onSubmit={handleSubmit}>
        <div>
          <label htmlFor="trialTitle">Trial Title</label>
          <br />

          <input
            id="trialTitle"
            type="text"
            value={trialTitle}
            onChange={(event) => setTrialTitle(event.target.value)}
            placeholder="Enter trial title"
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
            placeholder="Enter sponsor"
            required
          />
        </div>

        <button type="submit">
          Add Clinical Trial
        </button>
      </form>

      {error && <p>{error}</p>}
    </div>
  );
}

export default CreateRecord;